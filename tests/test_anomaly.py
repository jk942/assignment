from app.services.pipeline import PipelineService, calculate_median

def test_calculate_median():
    assert calculate_median([10.0]) == 10.0
    assert calculate_median([10.0, 20.0]) == 15.0
    assert calculate_median([30.0, 10.0, 20.0]) == 20.0
    assert calculate_median([]) == 0.0

def test_anomaly_detection_statistical_outlier():
    # 5 transactions for ACC001: median is 100
    # One outlier amount = 500 (which is > 3 * 100)
    txns = [
        {"txn_id": "T1", "amount": 100.0, "currency": "INR", "merchant": "Amazon", "account_id": "ACC001"},
        {"txn_id": "T2", "amount": 90.0, "currency": "INR", "merchant": "Amazon", "account_id": "ACC001"},
        {"txn_id": "T3", "amount": 110.0, "currency": "INR", "merchant": "Amazon", "account_id": "ACC001"},
        {"txn_id": "T4", "amount": 80.0, "currency": "INR", "merchant": "Amazon", "account_id": "ACC001"},
        {"txn_id": "T5", "amount": 500.0, "currency": "INR", "merchant": "Amazon", "account_id": "ACC001"},  # Outlier
    ]
    
    # Initialize basic keys
    for t in txns:
        t["is_anomaly"] = False
        t["anomaly_reason"] = None

    results = PipelineService.detect_anomalies(txns)

    # Median is 100.0. 3x is 300.0.
    # T5 (500.0) should be anomaly
    assert results[4]["is_anomaly"] is True
    assert "ACCOUNT_MEDIAN_OUTLIER" in results[4]["anomaly_reason"]

    # Others should not be anomalies
    for i in range(4):
        assert results[i]["is_anomaly"] is False

def test_anomaly_detection_currency_mismatch():
    txns = [
        # USD with domestic merchant
        {"txn_id": "T1", "amount": 50.0, "currency": "USD", "merchant": "Swiggy", "account_id": "ACC001"},
        # INR with domestic merchant
        {"txn_id": "T2", "amount": 50.0, "currency": "INR", "merchant": "Swiggy", "account_id": "ACC001"},
        # USD with international merchant
        {"txn_id": "T3", "amount": 50.0, "currency": "USD", "merchant": "Amazon", "account_id": "ACC001"},
    ]
    
    for t in txns:
        t["is_anomaly"] = False
        t["anomaly_reason"] = None

    results = PipelineService.detect_anomalies(txns)

    # T1: USD + Swiggy -> Anomaly
    assert results[0]["is_anomaly"] is True
    assert "CURRENCY_MERCHANT_MISMATCH" in results[0]["anomaly_reason"]

    # T2: INR + Swiggy -> Normal
    assert results[1]["is_anomaly"] is False

    # T3: USD + Amazon -> Normal
    assert results[2]["is_anomaly"] is False
