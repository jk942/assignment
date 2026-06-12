import pytest
from app.utils.helpers import (
    normalize_date,
    normalize_amount,
    normalize_currency,
    normalize_status
)
from app.services.pipeline import PipelineService

def test_date_normalization():
    assert normalize_date("04-09-2024") == "2024-09-04"
    assert normalize_date("2024/02/05") == "2024-02-05"
    assert normalize_date("2024-07-15") == "2024-07-15"
    assert normalize_date("  17/02/2024  ") == "2024-02-17"
    with pytest.raises(ValueError):
        normalize_date("invalid-date-format")

def test_amount_normalization():
    assert normalize_amount("$11325.79") == 11325.79
    assert normalize_amount("10882.55") == 10882.55
    assert normalize_amount(" $4,500.00 ") == 4500.00
    assert normalize_amount("") == 0.0

def test_currency_normalization():
    assert normalize_currency("inr") == "INR"
    assert normalize_currency("USD ") == "USD"

def test_status_normalization():
    assert normalize_status("success") == "SUCCESS"
    assert normalize_status("failed") == "FAILED"
    assert normalize_status("PENDING") == "PENDING"

def test_csv_cleaning_and_deduplication(tmp_path):
    # Setup a mock CSV file
    csv_data = (
        "txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
        "TXN1001,04-09-2024,Flipkart,10882.55,INR,SUCCESS,Shopping,ACC003,Refund expected\n"
        "TXN1002,2024/02/05,Swiggy,$11325.79,INR,success,Food,ACC004,\n"
        "TXN1001,04-09-2024,Flipkart,10882.55,INR,SUCCESS,Shopping,ACC003,Refund expected\n"  # Duplicate
        ",17-02-2024,Zomato,2536.35,usd,success,,ACC001,Verified\n"  # Missing category and txn_id
    )
    
    file_path = tmp_path / "test_transactions.csv"
    file_path.write_text(csv_data)

    txns, raw_count, clean_count, duplicates_removed = PipelineService.clean_transactions(str(file_path))

    # Verify counts
    assert raw_count == 4
    assert clean_count == 3
    assert duplicates_removed == 1

    # Verify normalization of TXN1001
    txn1 = next(t for t in txns if t["txn_id"] == "TXN1001")
    assert txn1["date"] == "2024-09-04"
    assert txn1["amount"] == 10882.55
    assert txn1["currency"] == "INR"
    assert txn1["status"] == "SUCCESS"
    assert txn1["category"] == "Shopping"

    # Verify normalization of TXN1002
    txn2 = next(t for t in txns if t["txn_id"] == "TXN1002")
    assert txn2["amount"] == 11325.79

    # Verify fallback for missing values
    txn3 = next(t for t in txns if t["txn_id"].startswith("TXN_GEN_"))
    assert txn3["date"] == "2024-02-17"
    assert txn3["category"] == "Uncategorised"
    assert txn3["currency"] == "USD"
    assert txn3["status"] == "SUCCESS"
