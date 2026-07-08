import pandas as pd
import numpy as np
from typing import Tuple, List, Dict

def load_data(pre_file: str, re_file: str, lookup_data: List[Dict]) -> Tuple[pd.DataFrame, List[str]]:
    """
    Loads, merges, cleans, and prepares the input data. It allocates entity costs
    BEFORE dropping records for names not found in the lookup data.
    
    Args:
        pre_file: Path to pre-invoice CSV file
        re_file: Path to re-invoice CSV file 
        lookup_data: List of dictionaries containing lookup data
    
    Returns:
        Tuple containing:
        - The cleaned, merged dataframe.
        - A list of names that were not found in the lookup data and were dropped.
    """
    # 1. Load and combine source files
    dfs_to_concat = []
    if pre_file:
        dfs_to_concat.append(pd.read_csv(pre_file))
    if re_file:
        dfs_to_concat.append(pd.read_csv(re_file))
    if not dfs_to_concat:
        return pd.DataFrame(), []
    
    merged_df = pd.concat(dfs_to_concat, ignore_index=True)
    
    # 2. Convert numeric columns to numbers EARLY
    float_cols = [
        'Base Salary [EUR]', 'Contribution [EUR]', 'Payslip Benefits [EUR]',
        'Expenses [EUR]', 'Incentives [EUR]', 'Other Benefits [EUR]', 'Total [EUR]'
    ]
    for col in float_cols:
        if col in merged_df.columns:
            # Ensure column exists before trying to convert
            merged_df[col] = merged_df[col].astype(str).str.replace(',', '', regex=False).replace('', '0')
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

    # 3. Merge with lookup data
    lookup_df = pd.DataFrame(lookup_data)
    join_df = pd.merge(merged_df, lookup_df, on="Name", how="left")

    # 4. ALLOCATE entity costs using the full list of employees
    entity_cost_names = ["Entity Cost", "Legal entity-wide cost"]
    if any(name in join_df["Name"].values for name in entity_cost_names):
        entity_cost_rows = join_df[join_df["Name"].isin(entity_cost_names)]
        total_cost = entity_cost_rows["Total [EUR]"].sum()

        # count only unique employees, excluding entity cost rows
        employee_names_df = join_df[~join_df["Name"].isin(entity_cost_names)]
        unique_employee_count = employee_names_df["Name"].nunique() 
        # --------------------------------------------------------------------

        team_plan_per_fte = total_cost / unique_employee_count if unique_employee_count > 0 else 0
        join_df["TEAM PLAN per FTE"] = np.where(
             ~join_df["Name"].isin(entity_cost_names), team_plan_per_fte, 0
        )
    else:
        join_df["TEAM PLAN per FTE"] = 0
        
    # 5. IDENTIFY and REMOVE unmatched employees AFTER allocation
    missing_mask = join_df['Kostenstelle I'].isna()
    if missing_mask.any():
        missing_names = join_df[missing_mask]['Name'].unique().tolist()
        join_df.dropna(subset=['Kostenstelle I'], inplace=True)
    else:
        missing_names = []
    
    # 6. Perform final column selection
    columns = [
        'Invoice number', 'Name', 'Type', 'Period', 'Issue date', 'Country', 'Start date',
        'Payslip FX Rate', 'Base Salary [EUR]', 'Contribution [EUR]',
        'Payslip Benefits [EUR]', 'Expenses [EUR]', 'Incentives [EUR]',
        'Other Benefits [EUR]', 'Total [EUR]', 'Kostenstelle I',
        'Kostenstellenbezeichnung I', 'Kostenstelle II', 'Kostenstellenbezeichnung II',
        'TEAM PLAN per FTE'
    ]

    for col in columns:
        if col not in join_df.columns:
            join_df[col] = 0
    
    final_df = join_df[columns].fillna(0)
    
    return final_df, missing_names  

def process_group(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Process data into pre-funding and estimate groups"""
    # Pre-funding processing
    pre_funding = df[df["Type"] == "Payroll pre-funding"]

    pre_group = pre_funding.groupby(
        [
        "Invoice number",
        "Name",
        "Period",
        "Issue date",
        "Kostenstelle I",
        "Kostenstellenbezeichnung I",
        "Kostenstelle II",
        "Kostenstellenbezeichnung II"
        ], dropna=False
    )["Total [EUR]"].sum().reset_index()

    pre_group.rename(columns={"Total [EUR]": "Total [EUR] I"}, inplace=True)
    pre_group["Total [EUR] II"] = 0

    # Estimate processing
    estimate_types = ["Previously billed as estimate", "Actual payroll services provided"]
    estimate = df[df["Type"].isin(estimate_types)].copy()

    # Create a summary of travel expenses per invoice/period
    expenses_summary = estimate.groupby(["Invoice number", "Period", "Issue date"])["Expenses [EUR]"].sum().reset_index()
    expenses_summary = expenses_summary[expenses_summary["Expenses [EUR]"] != 0]

    # Step 1: Group data first to get the NET amounts for each employee
    net_estimate = estimate.groupby(
        ['Invoice number', 'Name', 'Period'], dropna=False
    ).agg({
        'Issue date': 'first',
        'Total [EUR]': 'sum',
        'Incentives [EUR]': 'sum',
        'Expenses [EUR]': 'sum',
        'Kostenstelle I': 'first',
        'Kostenstellenbezeichnung I': 'first',
        'Kostenstelle II': 'first',
        'Kostenstellenbezeichnung II': 'first'
        }).reset_index()
    
    # Step 2: Get the unique Team Plan cost for each employee
    team_plan = estimate[estimate['TEAM PLAN per FTE'] > 0].groupby('Name')['TEAM PLAN per FTE'].first().reset_index()

    # Step 3: Merge the net totals with the Team Plan cost.
    # We remove the original "Entity Cost" rows here, as their cost is now in the 'TEAM PLAN per FTE' column.
    entity_cost_names = ["Entity Cost", "Legal entity-wide cost"]
    merged_estimate = pd.merge(
        net_estimate[~net_estimate['Name'].isin(entity_cost_names)],
        team_plan,
        on="Name",
        how="left"
    ).fillna(0)

    # Step 4: Perform the final calculation on the NETTED amounts.
    # This prevents the double-counting issue.
    merged_estimate["Total [EUR] I"] = (
        merged_estimate["Total [EUR]"]
        - merged_estimate["Incentives [EUR]"]
        + merged_estimate["TEAM PLAN per FTE"]
        - merged_estimate["Expenses [EUR]"]
    )
    
    merged_estimate["Total [EUR] II"] = merged_estimate["Incentives [EUR]"]
    
    # Final cleanup to match the required output format
    estimate_merged = merged_estimate.drop(columns=["Total [EUR]", "Expenses [EUR]", "Incentives [EUR]", "TEAM PLAN per FTE"])

    return pre_group, estimate_merged, expenses_summary

def create_datev_columns():
    """Create empty DataFrame with all DATEV columns"""
    columns = [
        'Umsatz (ohne Soll/Haben-Kz)', 'Soll/Haben-Kennzeichen', 'WKZ Umsatz', 'Kurs',
        'Basis-Umsatz', 'WKZ Basis-Umsatz', 'Konto', 'Gegenkonto (ohne BU-Schlüssel)',
        'BU-Schlüssel', 'Belegdatum', 'Belegfeld 1', 'Belegfeld 2', 'Skonto',
        'Buchungstext', 'Postensperre', 'Diverse Adressnummer', 'Geschäftspartnerbank',
        'Sachverhalt', 'Zinssperre', 'Beleglink'
    ] + [f'Beleginfo - Art {i}' for i in range(1, 9)] + [
        f'Beleginfo - Inhalt {i}' for i in range(1, 9)
    ] + ['KOST1 - Kostenstelle', 'KOST2 - Kostenstelle', 'Kost-Menge'] + [
        'Steuersatz'
    ]  # Added remaining columns as needed
    
    return pd.DataFrame(columns=columns)

def format_period(period):
    """Convert period to proper date format"""
    return pd.to_datetime(period).strftime('%d%m%Y')

def format_german_number(number):
    """Format number to German standard (comma as decimal separator)"""
    # 1. Take absolute value -> 2. Format with comma
    return f"{abs(number):,.2f}".replace(",", "").replace(".", ",")

def prepare_datev_row(row, kostenstelle_type='I'):
    """Prepare a single row for DATEV export"""
    amount = row[f'Total [EUR] {kostenstelle_type}']
    if amount == 0:
        return None
    
    # logic to conditionally add "bonus" to booking text
    buchungstext = f"Remote {pd.to_datetime(row['Period']).strftime('%m/%y')} {row['Name']}"
    if kostenstelle_type == 'II':
        # Check if description exists and doesn't contain 'Development'
        desc = row.get('Kostenstellenbezeichnung II', '')
        if 'Development' not in str(desc):
            buchungstext += " bonus"

    datev_row = {
        'Umsatz (ohne Soll/Haben-Kz)': format_german_number(amount),
        'Soll/Haben-Kennzeichen': 'S' if amount > 0 else 'H',
        'Konto': 4121,
        'Gegenkonto (ohne BU-Schlüssel)': 71707,
        'BU-Schlüssel': 94,
        'Belegdatum': format_period(row['Issue date']),
        'Belegfeld 1': row['Invoice number'].replace('#', ''),
        'Buchungstext': buchungstext,
        f'KOST1 - Kostenstelle': row[f'Kostenstelle {kostenstelle_type}'],
        'Steuersatz': 19
    }
    
    return datev_row

def process_datev_export(estimate_merged, expenses_summary=None):
    """Process the merged estimate data into DATEV format"""
    datev_df = create_datev_columns()
    datev_rows = []
    
    for _, row in estimate_merged.iterrows():
        # Process Kostenstelle I
        kost_i_row = prepare_datev_row(row, 'I')
        if kost_i_row:
            datev_rows.append(kost_i_row)
            
        # Process Kostenstelle II
        kost_ii_row = prepare_datev_row(row, 'II')
        if kost_ii_row:
            datev_rows.append(kost_ii_row)
    
    if expenses_summary is not None and not expenses_summary.empty: 
        for _, expense_row in expenses_summary.iterrows():
            amount = expense_row['Expenses [EUR]']
            if amount == 0:
                continue
                
            travel_expense_datev_row = {
                'Umsatz (ohne Soll/Haben-Kz)': format_german_number(amount),
                'Soll/Haben-Kennzeichen': 'S' if amount > 0 else 'H',
                'Konto': 4121,
                'Gegenkonto (ohne BU-Schlüssel)': 71707,
                'BU-Schlüssel': 94,
                'Belegdatum': format_period(expense_row['Issue date']),
                'Belegfeld 1': str(expense_row['Invoice number']).replace('#', ''),
                'Buchungstext': 'Remote Travel Expenses',
                'KOST1 - Kostenstelle': 410, # Assign to the specified cost center
                'Steuersatz': 19
            }
            datev_rows.append(travel_expense_datev_row)
    
    result_df = pd.DataFrame(datev_rows)
    
    for col in datev_df.columns:
        if col not in result_df.columns:
            result_df[col] = ''
            
    return result_df[datev_df.columns]


# def export_to_csv(df: pd.DataFrame, filename: str) -> None:
#     """Export dataframe to CSV with proper encoding"""
#     df.to_csv(
#         filename,
#         index=False,
#         encoding='utf-8-sig',
#         sep=';',
#         quoting=1
#     )

# def main():
#     """Main execution function"""
#     # File paths
#     pre_file = "2025-09-Invoice-050IN25081745-Hygraph-Gmb-H.csv"
#     re_file = "2025-08-Invoice-050IN25086667-Hygraph-Gmb-H.csv"
    
#     # Process data
#     join_df = load_data(pre_file, re_file, lookup_dict)
#     pre_group, estimate_merged = process_group(join_df)
    
#     # Export results
#     export_files = {
#         'pre_group_summary.csv': pre_group,
#         'estimate_merged_summary.csv': estimate_merged,
#     }
    
#     for filename, df in export_files.items():
#         export_to_csv(df, filename)
#         print(f"Exported {filename}")

# if __name__ == "__main__":
#     main()