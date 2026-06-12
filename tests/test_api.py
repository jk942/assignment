import pytest
from datetime import datetime
from decimal import Decimal
from app.models.job import Job, JobSummary
from app.models.transaction import Transaction

def test_upload_csv_success(client, mock_celery):
    csv_content = (
        "txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
        "TXN1001,04-09-2024,Flipkart,10882.55,INR,SUCCESS,Shopping,ACC003,Refund expected\n"
    )
    
    files = {"file": ("transactions.csv", csv_content, "text/csv")}
    response = client.post("/jobs/upload", files=files)
    
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    mock_celery.assert_called_once()

def test_upload_invalid_extension(client):
    files = {"file": ("transactions.txt", "some,text,data", "text/plain")}
    response = client.post("/jobs/upload", files=files)
    
    assert response.status_code == 400
    assert "Invalid file extension" in response.json()["detail"]

def test_upload_empty_file(client):
    files = {"file": ("transactions.csv", "", "text/csv")}
    response = client.post("/jobs/upload", files=files)
    
    assert response.status_code == 400
    assert "Empty file" in response.json()["detail"]

def test_get_job_status_pending(client, db_session):
    # Seed a pending job
    job = Job(id="job-pending-123", filename="test.csv", status="pending")
    db_session.add(job)
    db_session.commit()

    response = client.get("/jobs/job-pending-123/status")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "job-pending-123"
    assert data["status"] == "pending"
    assert data["summary"] is None

def test_get_job_status_completed(client, db_session):
    # Seed a completed job with summary
    job = Job(id="job-comp-123", filename="test.csv", status="completed")
    db_session.add(job)
    db_session.commit()

    summary = JobSummary(
        job_id="job-comp-123",
        total_spend_inr=Decimal("15000.50"),
        total_spend_usd=Decimal("250.00"),
        top_merchants=[{"merchant": "Flipkart", "total_spend": 15000.50}],
        anomaly_count=1,
        narrative="Test narrative spending",
        risk_level="medium"
    )
    db_session.add(summary)
    db_session.commit()

    response = client.get("/jobs/job-comp-123/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["summary"]["total_spend_inr"] == 15000.50
    assert data["summary"]["risk_level"] == "medium"

def test_get_job_results_not_completed(client, db_session):
    job = Job(id="job-pending-123", filename="test.csv", status="processing")
    db_session.add(job)
    db_session.commit()

    response = client.get("/jobs/job-pending-123/results")
    assert response.status_code == 400
    assert "results are only available for 'completed' jobs" in response.json()["detail"].lower()

def test_get_job_results_success(client, db_session):
    # Seed job, summary, and transactions
    job = Job(id="job-comp-123", filename="test.csv", status="completed")
    db_session.add(job)
    
    summary = JobSummary(
        job_id="job-comp-123",
        total_spend_inr=Decimal("15000.50"),
        total_spend_usd=Decimal("250.00"),
        top_merchants=[{"merchant": "Flipkart", "total_spend": 15000.50}],
        anomaly_count=1,
        narrative="Test narrative",
        risk_level="medium"
    )
    db_session.add(summary)

    # 1 normal transaction, 1 anomaly
    t1 = Transaction(
        id="t-1",
        job_id="job-comp-123",
        txn_id="TXN001",
        date=datetime.strptime("2024-09-04", "%Y-%m-%d").date(),
        merchant="Flipkart",
        amount=Decimal("15000.50"),
        currency="INR",
        status="SUCCESS",
        category="Shopping",
        account_id="ACC003",
        is_anomaly=False
    )
    t2 = Transaction(
        id="t-2",
        job_id="job-comp-123",
        txn_id="TXN002",
        date=datetime.strptime("2024-02-05", "%Y-%m-%d").date(),
        merchant="Swiggy",
        amount=Decimal("250.00"),
        currency="USD",
        status="SUCCESS",
        category="Food",
        account_id="ACC004",
        is_anomaly=True,
        anomaly_reason="CURRENCY_MERCHANT_MISMATCH"
    )
    db_session.add(t1)
    db_session.add(t2)
    db_session.commit()

    response = client.get("/jobs/job-comp-123/results")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["cleaned_transactions"]) == 1
    assert data["cleaned_transactions"][0]["txn_id"] == "TXN001"
    
    assert len(data["flagged_anomalies"]) == 1
    assert data["flagged_anomalies"][0]["txn_id"] == "TXN002"
    assert data["flagged_anomalies"][0]["anomaly_reason"] == "CURRENCY_MERCHANT_MISMATCH"
    
    assert data["category_breakdown"] == {"Shopping": 1, "Food": 1}
    assert data["llm_summary"]["risk_level"] == "medium"
    assert data["llm_summary"]["top_3_merchants"] == ["Flipkart"]

def test_list_jobs(client, db_session):
    job1 = Job(id="j-1", filename="a.csv", status="completed", row_count_clean=10, created_at=datetime(2026, 6, 12, 10, 0))
    job2 = Job(id="j-2", filename="b.csv", status="pending", row_count_raw=5, created_at=datetime(2026, 6, 12, 11, 0))
    db_session.add(job1)
    db_session.add(job2)
    db_session.commit()

    # Get all jobs
    response = client.get("/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Check ordering (descending by created_at)
    assert data[0]["job_id"] == "j-2"
    assert data[0]["row_count"] == 5
    assert data[1]["job_id"] == "j-1"
    assert data[1]["row_count"] == 10

    # Filter by status
    response_filter = client.get("/jobs?status=completed")
    assert response_filter.status_code == 200
    data_filter = response_filter.json()
    assert len(data_filter) == 1
    assert data_filter[0]["job_id"] == "j-1"
