import csv
import uuid
from typing import List, Dict, Any, Tuple
from app.utils.helpers import (
    normalize_date,
    normalize_amount,
    normalize_currency,
    normalize_status
)

def calculate_median(amounts: List[float]) -> float:
    """
    Computes the median of a list of floats.
    """
    if not amounts:
        return 0.0
    sorted_amounts = sorted(amounts)
    n = len(sorted_amounts)
    mid = n // 2
    if n % 2 == 1:
        return sorted_amounts[mid]
    else:
        return (sorted_amounts[mid - 1] + sorted_amounts[mid]) / 2.0

class PipelineService:
    @staticmethod
    def clean_transactions(file_path: str) -> Tuple[List[Dict[str, Any]], int, int, int]:
        """
        Reads a CSV file, cleans and normalizes transaction data, and removes duplicates.
        Returns (cleaned_transactions, raw_count, clean_count, duplicates_removed).
        """
        raw_count = 0
        duplicates_removed = 0
        seen_rows = set()
        cleaned_transactions = []

        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # We identify exact duplicates by matching the raw string values of all columns.
                # Remove spaces from keys and values for robustness.
                row_cleaned_keys = {k.strip(): (v.strip() if v is not None else "") for k, v in row.items() if k is not None}
                
                # Make a hashable representation of the row to find exact duplicate rows
                row_tuple = tuple(sorted(row_cleaned_keys.items()))
                
                raw_count += 1
                if row_tuple in seen_rows:
                    duplicates_removed += 1
                    continue
                seen_rows.add(row_tuple)

                # Core data cleaning
                # 1. Handle missing/blank txn_id
                txn_id = row_cleaned_keys.get("txn_id", "")
                if not txn_id:
                    txn_id = f"TXN_GEN_{uuid.uuid4()}"

                # 2. Normalize date
                date_str = row_cleaned_keys.get("date", "")
                try:
                    normalized_date = normalize_date(date_str)
                except Exception:
                    # If date parsing fails, default to a fallback or raise
                    # For this exercise, let's fall back to none and log or raise
                    raise ValueError(f"Invalid date format: {date_str}")

                # 3. Clean amount (strip $ and parse)
                amount_str = row_cleaned_keys.get("amount", "0.0")
                amount = normalize_amount(amount_str)

                # 4. Normalize currency
                currency_str = row_cleaned_keys.get("currency", "INR")
                currency = normalize_currency(currency_str)

                # 5. Normalize status
                status_str = row_cleaned_keys.get("status", "PENDING")
                status = normalize_status(status_str)

                # 6. Fill missing categories with "Uncategorised"
                category = row_cleaned_keys.get("category", "")
                if not category or category.lower() == "uncategorised":
                    category = "Uncategorised"

                account_id = row_cleaned_keys.get("account_id", "ACC_UNKNOWN")

                cleaned_row = {
                    "txn_id": txn_id,
                    "date": normalized_date,
                    "merchant": row_cleaned_keys.get("merchant", "Unknown"),
                    "amount": amount,
                    "currency": currency,
                    "status": status,
                    "category": category,
                    "account_id": account_id,
                    "is_anomaly": False,
                    "anomaly_reason": None
                }
                cleaned_transactions.append(cleaned_row)

        clean_count = len(cleaned_transactions)
        return cleaned_transactions, raw_count, clean_count, duplicates_removed

    @staticmethod
    def detect_anomalies(transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Runs the anomaly detection rules on a list of cleaned transactions:
        1. Statistical Outlier: amount > 3 * median(account_id)
        2. Domestic Merchant Currency Mismatch: currency = USD and merchant in Swiggy, Ola, IRCTC
        """
        # Group transaction amounts by account_id for median calculation
        account_groups = {}
        for txn in transactions:
            acc_id = txn["account_id"]
            if acc_id not in account_groups:
                account_groups[acc_id] = []
            account_groups[acc_id].append(txn["amount"])

        # Calculate medians
        account_medians = {acc_id: calculate_median(amounts) for acc_id, amounts in account_groups.items()}

        # Flag anomalies
        domestic_brands = {"Swiggy", "Ola", "IRCTC"}

        for txn in transactions:
            acc_id = txn["account_id"]
            amount = txn["amount"]
            currency = txn["currency"]
            merchant = txn["merchant"]

            reasons = []

            # Rule 1: Statistical outlier
            median_val = account_medians.get(acc_id, 0.0)
            if amount > 3 * median_val:
                reasons.append("ACCOUNT_MEDIAN_OUTLIER")

            # Rule 2: Domestic Merchant Currency Mismatch
            # Swiggy, Ola, IRCTC are domestic-only brands. If currency is USD, flag it.
            if currency == "USD" and merchant in domestic_brands:
                reasons.append("CURRENCY_MERCHANT_MISMATCH")

            if reasons:
                txn["is_anomaly"] = True
                txn["anomaly_reason"] = ", ".join(reasons)

        return transactions
