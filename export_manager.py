"""
Export manager - thin coordinator for all export functionality.
This module provides a clean interface for app.py to use export features.
All export logic is delegated to specific modules (clipboard_export).
"""
import pandas as pd
from clipboard_export import prepare_csv_data, copy_to_clipboard


def prepare_export_dataframe(basket_data):
    """
    Prepares basket data for export by converting to DataFrame and formatting.
    
    Args:
        basket_data: List of contact dictionaries from basket
        
    Returns:
        pandas.DataFrame: Formatted DataFrame ready for export
    """
    if not basket_data:
        return pd.DataFrame()
    
    # Create DataFrame from basket data
    export_df = pd.DataFrame(basket_data)
    
    # Ensure company column exists (extract from organization dict if needed)
    if 'organization' in export_df.columns:
        export_df['company'] = export_df['organization'].apply(
            lambda x: x.get('name') if isinstance(x, dict) else str(x) if x else 'N/A'
        )
    elif 'company' not in export_df.columns:
        export_df['company'] = 'N/A'
    
    # Ensure last_name column exists (use last_name_obfuscated if needed)
    if 'last_name' not in export_df.columns:
        if 'last_name_obfuscated' in export_df.columns:
            export_df['last_name'] = export_df['last_name_obfuscated']
        else:
            export_df['last_name'] = ''
    
    # Select columns for export: first_name, last_name, company, title, email
    csv_cols = ['first_name', 'last_name', 'company', 'title', 'email']
    available_cols = [c for c in csv_cols if c in export_df.columns]
    
    return export_df[available_cols]


def export_to_clipboard(basket_data):
    """
    Exports basket data to clipboard format (tab-separated string without headers).
    
    Args:
        basket_data: List of contact dictionaries from basket
        
    Returns:
        str: Tab-separated string ready for clipboard (no headers)
    """
    export_df = prepare_export_dataframe(basket_data)
    tsv_string = prepare_csv_data(export_df)
    return copy_to_clipboard(tsv_string)

