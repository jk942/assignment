import os
import logging
from datetime import datetime
from decimal import Decimal
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.job import Job, JobSummary
from app.models.transaction import Transaction
from app.services.pipeline import PipelineService

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.pipeline_tasks.process_transaction_file")
def process_transaction_file(job_id: str) -> str:
    """
    Asynchronously processes the uploaded transaction CSV file:
    1. Reads and cleans transactions.
    2. Runs anomaly detection.
    3. Saves all transactions and summary to PostgreSQL.
    """
    logger.info(f"Starting processing pipeline for Job: {job_id}")
    db = SessionLocal()
    
    # Fetch job record
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return f"Job {job_id} not found."

    try:
        # Update job status to processing
        job.status = "processing"
        db.commit()

        # Build absolute path to the uploaded CSV file
        from app.core.config import settings
        file_path = os.path.join(settings.UPLOAD_DIR, f"{job_id}.csv")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded file not found at: {file_path}")

        # Step 1 & 2: Clean data and detect anomalies
        logger.info(f"Step 1 & 2: Cleaning and anomaly detection for Job {job_id}")
        cleaned_txns, raw_count, clean_count, duplicates_removed = PipelineService.clean_transactions(file_path)
        PipelineService.detect_anomalies(cleaned_txns)

        # Calculate aggregate metrics for summary
        spend_by_currency = {"USD": 0.0, "INR": 0.0}
        merchant_spend = {}
        anomaly_count = 0

        for t in cleaned_txns:
            curr = t["currency"]
            amt = t["amount"]
            merchant = t["merchant"]
            
            # Spend by currency
            if curr in spend_by_currency:
                spend_by_currency[curr] += amt
            else:
                spend_by_currency[curr] = amt
                
            # Merchant spend frequency/amount
            merchant_spend[merchant] = merchant_spend.get(merchant, 0.0) + amt
            
            # Anomaly count
            if t["is_anomaly"]:
                anomaly_count += 1

        # Format top merchants sorted by total amount
        top_merchants_list = sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:3]
        top_merchants_json = [{"merchant": m, "total_spend": amt} for m, amt in top_merchants_list]

        # Step 3: Save results to database
        logger.info(f"Step 3: Saving cleaned transactions to PostgreSQL for Job {job_id}")
        
        # Save transactions
        db_transactions = []
        for t in cleaned_txns:
            db_txn = Transaction(
                job_id=job_id,
                txn_id=t["txn_id"],
                date=datetime.strptime(t["date"], "%Y-%m-%d").date(),
                merchant=t["merchant"],
                amount=Decimal(str(t["amount"])),
                currency=t["currency"],
                status=t["status"],
                category=t["category"],
                account_id=t["account_id"],
                is_anomaly=t["is_anomaly"],
                anomaly_reason=t["anomaly_reason"]
            )
            db.add(db_txn)
            db_transactions.append(db_txn)

        # Save JobSummary
        db_summary = JobSummary(
            job_id=job_id,
            total_spend_inr=Decimal(str(spend_by_currency.get("INR", 0.0))),
            total_spend_usd=Decimal(str(spend_by_currency.get("USD", 0.0))),
            top_merchants=top_merchants_json,
            anomaly_count=anomaly_count
        )
        db.add(db_summary)

        # Update job record with details
        job.status = "completed"
        job.row_count_raw = raw_count
        job.row_count_clean = clean_count
        job.completed_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Job {job_id} successfully completed. Raw: {raw_count}, Clean: {clean_count}")
        return f"Job {job_id} completed successfully."

    except Exception as e:
        logger.exception(f"Unhandled exception in pipeline for Job {job_id}")
        db.rollback()
        
        # Set job status to failed and store the error message
        job.status = "failed"
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        
        return f"Job {job_id} failed: {str(e)}"
    finally:
        db.close()
