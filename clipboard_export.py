"""
Clipboard export module for copying tab-separated data to clipboard.
This module is isolated and can be easily replaced.
"""
import pandas as pd


def prepare_csv_data(dataframe):
    """
    Converts a DataFrame to tab-separated string format (without headers).
    
    Args:
        dataframe: pandas DataFrame with contact data
        
    Returns:
        str: Tab-separated string (no headers)
    """
    if dataframe is None or dataframe.empty:
        return ""
    
    # Convert to tab-separated string without index and without headers
    tsv_string = dataframe.to_csv(index=False, sep='\t', header=False)
    return tsv_string


def copy_to_clipboard(tsv_string):
    """
    Prepares tab-separated string for clipboard copy.
    Note: In Streamlit, we can't directly copy to clipboard due to browser limitations.
    This function returns the TSV string that can be displayed in a code block
    with a copy button, or used with JavaScript-based clipboard functionality.
    
    Args:
        tsv_string: Tab-separated string (no headers)
        
    Returns:
        str: TSV string ready for clipboard (or display in Streamlit)
    """
    return tsv_string

