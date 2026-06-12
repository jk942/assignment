import os
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from app.models.job import Job, JobSummary
from app.models.transaction import Transaction
from app.tasks.pipeline_tasks import process_transaction_file

def test_celery_pipeline_task_success(db_session, tmp_path):
    # Setup mock file
    csv_data = (
        "txn_id,date,merchant,amount,currency,status,category,account_id,notes\n"
        "TXN1000,04-09-2024,Flipkart,100.00,INR,SUCCESS,,ACC003,\n"  # missing category
        "TXN1001,2024/02/05,Swiggy,10.00,INR,success,Food,ACC003,\n"
        "TXN1001,2024/02/05,Swiggy,10.00,INR,success,Food,ACC003,\n"   # duplicate
        "TXN1002,17-02-2024,Swiggy,500.00,USD,success,Food,ACC003,\n"  # USD Swiggy (anomaly) & Outlier (>3 * median)
    )
    
    job_id = "test-job-celery-123"
    
    # Write CSV file to the upload path
    from app.core.config import settings
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{job_id}.csv")
    with open(file_path, "w") as f:
        f.write(csv_data)

    try:
        # Seed a pending job
        job = Job(id=job_id, filename="transactions.csv", status="pending")
        db_session.add(job)
        db_session.commit()

        # Run task
        result = process_transaction_file(job_id)
        assert "completed successfully" in result

        # Refresh job from DB
        db_session.expire_all()
        job = db_session.query(Job).filter(Job.id == job_id).first()
        assert job.status == "completed"
        assert job.row_count_raw == 4
        assert job.row_count_clean == 3

        # Verify transactions saved
        txns = db_session.query(Transaction).filter(Transaction.job_id == job_id).all()
        assert len(txns) == 3

        # Verify duplicate removed
        assert len([t for t in txns if t.txn_id == "TXN1001"]) == 1

        # Verify category classification via LLM
        txn1000 = next(t for t in txns if t.txn_id == "TXN1000")
        assert txn1000.category in {"Shopping", "Other"}
        assert txn1000.llm_category == txn1000.category
        assert txn1000.llm_failed is False

        # Verify anomalies detected
        txn1002 = next(t for t in txns if t.txn_id == "TXN1002")
        assert txn1002.is_anomaly is True
        assert "CURRENCY_MERCHANT_MISMATCH" in txn1002.anomaly_reason
        assert "ACCOUNT_MEDIAN_OUTLIER" in txn1002.anomaly_reason

        # Verify summary stats
        summary = db_session.query(JobSummary).filter(JobSummary.job_id == job_id).first()
        assert summary is not None
        assert float(summary.total_spend_inr) == 110.0
        assert float(summary.total_spend_usd) == 500.0
        assert summary.anomaly_count == 1

    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
