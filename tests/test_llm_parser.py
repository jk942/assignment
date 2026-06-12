import pytest
from unittest.mock import patch
from app.services.gemini import GeminiLLMService

def test_gemini_classify_categories_success():
    service = GeminiLLMService(api_key="mock-key")
    
    mock_response = """
    {
      "classifications": [
        {"txn_id": "TXN1", "category": "Food"},
        {"txn_id": "TXN2", "category": "Shopping"},
        {"txn_id": "TXN3", "category": "InvalidCategory"}
      ]
    }
    """
    
    with patch.object(service, "_call_gemini_api", return_value=mock_response) as mock_call:
        input_txns = [
            {"txn_id": "TXN1", "merchant": "Swiggy"},
            {"txn_id": "TXN2", "merchant": "Amazon"},
            {"txn_id": "TXN3", "merchant": "Unknown"}
        ]
        
        results = service.classify_categories(input_txns)
        
        mock_call.assert_called_once()
        assert results["TXN1"] == "Food"
        assert results["TXN2"] == "Shopping"
        # Invalid category should fall back to "Other"
        assert results["TXN3"] == "Other"

def test_gemini_generate_summary_success():
    service = GeminiLLMService(api_key="mock-key")
    
    mock_response = """
    {
      "total_spend_by_currency": {"INR": 150000.0, "USD": 200.0},
      "top_3_merchants": ["Flipkart", "IRCTC", "Amazon"],
      "anomaly_count": 1,
      "narrative": "Spending trends are high on local Indian brands. One anomaly was detected due to currency mismatch.",
      "risk_level": "medium"
    }
    """
    
    with patch.object(service, "_call_gemini_api", return_value=mock_response) as mock_call:
        results = service.generate_summary(
            spend_by_currency={"INR": 150000.0, "USD": 200.0},
            top_merchants=[{"merchant": "Flipkart", "total_spend": 100000}, {"merchant": "IRCTC", "total_spend": 50000}],
            anomaly_count=1
        )
        
        mock_call.assert_called_once()
        assert results["risk_level"] == "medium"
        assert results["anomaly_count"] == 1
        assert "Flipkart" in results["top_3_merchants"]
        assert "currency mismatch" in results["narrative"]
