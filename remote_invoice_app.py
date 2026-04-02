import streamlit as st
import pandas as pd
import datetime
from invoice_processor import load_data, process_group, process_datev_export

# --- Page Configuration ---
st.set_page_config(
    page_title="Invoice Processor",
    page_icon="⚙️",
    layout="wide"
)

# --- Initialize Session State ---
if 'results' not in st.session_state:
    st.session_state.results = {}
if 'history' not in st.session_state:
    st.session_state.history = []

# --- Sidebar Navigation ---
with st.sidebar:
    st.title("InvoiceProcessor")
    st.write("Professional Data Processing")
    
    page_selection = st.radio(
        "TOOLS",
        ["Process Files", "Job History"]
    )
    st.info("App by Santiago.")

# --- Page Rendering Functions ---

def show_process_files_page():
    st.title("Invoice Data Processor")
    st.markdown("Upload your pre-invoice and re-invoice CSV files to automatically process and generate grouped summaries.")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            pre_file = st.file_uploader("Pre-Invoice File (.csv)", type="csv")
        with col2:
            re_file = st.file_uploader("Re-Invoice File (.csv)", type="csv")

    if pre_file or re_file:
        if st.button("Process Files", type="primary", use_container_width=True):
            with st.spinner("Processing data..."):
                try:
                    # --- CHANGE START ---
                    # 1. Load data and capture the list of missing names
                    lookup_dict = st.secrets["lookup_data"]
                    join_df, missing_names = load_data(pre_file, re_file, lookup_dict)
                    
                    # 2. Display a warning if any names were dropped
                    if missing_names:
                        st.warning(f"⚠️ The following names were not found in the lookup data and have been dropped: {', '.join(missing_names)}")
                    # --- CHANGE END ---
                    
                    # 3. Process the cleaned data
                    pre_group, estimate_merged, expenses_summary = process_group(join_df)
                    pre_datev = process_datev_export(pre_group)
                    estimate_datev = process_datev_export(estimate_merged, expenses_summary)

                    st.session_state.results = {
                        "pre_group": pre_group, "estimate_merged": estimate_merged,
                        "pre_datev": pre_datev, "estimate_datev": estimate_datev
                    }
                    st.session_state.history.append({
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "pre_invoice_file": pre_file.name if pre_file else "N/A",
                        "re_invoice_file": re_file.name if re_file else "N/A",
                        "records_processed": len(join_df)
                    })
                    st.success("✔ Processing complete! Results are shown below.")
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    st.session_state.results = {}

    if st.session_state.results:
        st.markdown("---")
        st.header("Results")

        # Retrieve results safely
        pre_group_df = st.session_state.results.get("pre_group")
        estimate_merged_df = st.session_state.results.get("estimate_merged")
        pre_datev_df = st.session_state.results.get("pre_datev")
        estimate_datev_df = st.session_state.results.get("estimate_datev")

        st.subheader("Standard Summaries")
        res_col1, res_col2 = st.columns(2)
        with res_col1:
            # Only show if the dataframe exists and is not empty
            if pre_group_df is not None and not pre_group_df.empty:
                st.caption("Pre-Group Summary")
                st.dataframe(pre_group_df)
        with res_col2:
            if estimate_merged_df is not None and not estimate_merged_df.empty:
                st.caption("Estimate Merged Summary")
                st.dataframe(estimate_merged_df)

        st.subheader("DATEV Export Previews")
        datev_col1, datev_col2 = st.columns(2)
        with datev_col1:
            if pre_datev_df is not None and not pre_datev_df.empty:
                st.caption("Pre-Group DATEV Export")
                st.dataframe(pre_datev_df)
        with datev_col2:
            if estimate_datev_df is not None and not estimate_datev_df.empty:
                st.caption("Estimate DATEV Export (with Travel Expenses)")
                st.dataframe(estimate_datev_df)

        st.markdown("---")
        st.subheader("Download Available Files")
        
        dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)
        
        if pre_group_df is not None and not pre_group_df.empty:
            pre_group_csv = pre_group_df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            with dl_col1:
                st.download_button("Download Pre-Group Summary", pre_group_csv, "pre_group_summary.csv", "text/csv", use_container_width=True)

        if estimate_merged_df is not None and not estimate_merged_df.empty:
            estimate_merged_csv = estimate_merged_df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            with dl_col2:
                st.download_button("Download Estimate Summary", estimate_merged_csv, "estimate_merged_summary.csv", "text/csv", use_container_width=True)

        if pre_datev_df is not None and not pre_datev_df.empty:
            pre_datev_csv = pre_datev_df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            with dl_col3:
                st.download_button("Download Pre-Group DATEV", pre_datev_csv, "pre_datev_export.csv", "text/csv", use_container_width=True, type="primary")

        if estimate_datev_df is not None and not estimate_datev_df.empty:
            estimate_datev_csv = estimate_datev_df.to_csv(index=False, sep=';', encoding='utf-8-sig').encode('utf-8-sig')
            with dl_col4:
                st.download_button("Download Estimate DATEV", estimate_datev_csv, "estimate_datev_export.csv", "text/csv", use_container_width=True, type="primary")

def show_job_history_page():
    st.title("🕒 Job History (Current Session)")
    st.markdown("This shows a history of files processed since opening the app.")
    if st.session_state.history:
        history_df = pd.DataFrame(st.session_state.history).sort_values(by="time", ascending=False)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.info("No files have been processed in this session yet.")

# --- Main App Logic ---
if page_selection == "Process Files":
    show_process_files_page()
elif page_selection == "Job History":
    show_job_history_page()