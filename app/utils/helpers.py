import datetime
import re

def normalize_date(date_str: str) -> str:
    """
    Normalizes date string to YYYY-MM-DD format.
    Supports:
    - DD-MM-YYYY (e.g., 04-09-2024)
    - YYYY/MM/DD (e.g., 2024/02/05)
    - YYYY-MM-DD (e.g., 2024-07-15)
    - DD/MM/YYYY (fallback)
    """
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d/%m/%Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: '{date_str}'")

def normalize_amount(amount_str: str) -> float:
    """
    Strips '$' and commas, and converts amount to float.
    """
    if not amount_str:
        return 0.0
    cleaned = amount_str.strip().replace("$", "").replace(",", "")
    return float(cleaned)

def normalize_currency(currency_str: str) -> str:
    """
    Normalizes currency (e.g., 'inr' -> 'INR').
    """
    return currency_str.strip().upper()

def normalize_status(status_str: str) -> str:
    """
    Normalizes transaction status (e.g., 'success' -> 'SUCCESS').
    """
    return status_str.strip().upper()
