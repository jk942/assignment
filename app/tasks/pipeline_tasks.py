import os
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.job import Job, JobSummary
from app.models.transaction import Transaction
from app.services.pipeline import PipelineService
from app.services.gemini import GeminiLLMService
from app.core.config import settings

logger = logging.getLogger(__name__)

@celery_app.task(name="app.tasks.pipeline_tasks.process_transaction_file")
def process_transaction_file(job_id: str) -> str:
    """
    Asynchronously processes the uploaded transaction CSV file:
    1. Reads and cleans transactions.
    2. Runs anomaly detection.
    3. Uses Gemini to classify missing categories and generate a summary.
    4. Saves all records to PostgreSQL.
    """
    logger.info(f"Starting processing pipeline for Job: {job_id}")
    db = SessionLocal()
    
    # Fetch job record
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        db.close()
        return f"Job {job_id} not found."

    try:
        job.status = "processing"
        db.commit()

        file_path = os.path.join(settings.UPLOAD_DIR, f"{job_id}.csv")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Uploaded file not found at: {file_path}")

        logger.info(f"Step 1: Cleaning transaction data for Job {job_id}")
        cleaned_txns, raw_count, clean_count, duplicates_removed = PipelineService.clean_transactions(file_path)

        logger.info(f"Step 2: Detecting anomalies for Job {job_id}")
        PipelineService.detect_anomalies(cleaned_txns)

        logger.info(f"Step 3: Classifying missing categories with Gemini for Job {job_id}")
        gemini_service = GeminiLLMService()
        uncategorised_transactions = [txn for txn in cleaned_txns if txn["category"] == "Uncategorised"]
        classification_raw = ""
        if uncategorised_transactions:
            try:
                classification_result = gemini_service.classify_categories(
                    uncategorised_transactions,
                    return_raw=True,
                )
                classification_raw = classification_result.get("raw_response", "")
                category_map = classification_result.get("categories", {})
                for txn in uncategorised_transactions:
                    predicted = category_map.get(txn["txn_id"], "Other")
                    txn["category"] = predicted
                    txn["llm_category"] = predicted
                    txn["llm_raw_response"] = classification_raw
                    txn["llm_failed"] = False
            except Exception as exc:
                classification_raw = str(exc)
                for txn in uncategorised_transactions:
                    txn["llm_category"] = "Other"
                    txn["llm_raw_response"] = classification_raw
                    txn["llm_failed"] = True

        spend_by_currency = {"USD": 0.0, "INR": 0.0}
        merchant_spend: Dict[str, float] = {}
        anomaly_count = 0

        for txn in cleaned_txns:
            curr = txn["currency"]
            amount = txn["amount"]
            merchant = txn["merchant"]

            spend_by_currency[curr] = spend_by_currency.get(curr, 0.0) + amount
            merchant_spend[merchant] = merchant_spend.get(merchant, 0.0) + amount
            if txn["is_anomaly"]:
                anomaly_count += 1

        top_merchants_list = sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:3]
        top_merchants_json = [{"merchant": m, "total_spend": amt} for m, amt in top_merchants_list]

        llm_summary_data = {}
        try:
            llm_summary_data = gemini_service.generate_summary(
                spend_by_currency=spend_by_currency,
                top_merchants=top_merchants_json,
                anomaly_count=anomaly_count,
            )
        except Exception as exc:
            logger.warning("Gemini summary generation failed for Job %s: %s", job_id, exc)
            llm_summary_data = {
                "total_spend_by_currency": spend_by_currency,
                "top_3_merchants": [m[0] for m in top_merchants_list],
                "anomaly_count": anomaly_count,
                "narrative": "Summary generation failed. The batch was processed but LLM summary could not be completed.",
                "risk_level": "medium"
            }

        logger.info(f"Step 4: Saving processed records for Job {job_id}")
        for txn in cleaned_txns:
            db_txn = Transaction(
                job_id=job_id,
                txn_id=txn["txn_id"],
                date=datetime.strptime(txn["date"], "%Y-%m-%d").date(),
                merchant=txn["merchant"],
                amount=Decimal(str(txn["amount"])),
                currency=txn["currency"],
                status=txn["status"],
                category=txn["category"],
                account_id=txn["account_id"],
                is_anomaly=txn["is_anomaly"],
                anomaly_reason=txn["anomaly_reason"],
                llm_category=txn.get("llm_category"),
                llm_raw_response=txn.get("llm_raw_response"),
                llm_failed=txn.get("llm_failed", False)
            )
            db.add(db_txn)

        db_summary = JobSummary(
            job_id=job_id,
            total_spend_inr=Decimal(str(spend_by_currency.get("INR", 0.0))),
            total_spend_usd=Decimal(str(spend_by_currency.get("USD", 0.0))),
            top_merchants=top_merchants_json,
            anomaly_count=anomaly_count,
            narrative=llm_summary_data.get("narrative", ""),
            risk_level=llm_summary_data.get("risk_level", "low")
        )
        db.add(db_summary)

        job.status = "completed"
        job.row_count_raw = raw_count
        job.row_count_clean = clean_count
        job.completed_at = datetime.utcnow()
        db.commit()

        logger.info(
            "Job %s successfully completed. Raw count=%s, Clean count=%s, Duplicates removed=%s",
            job_id,
            raw_count,
            clean_count,
            duplicates_removed,
        )
        return f"Job {job_id} completed successfully."

    except Exception as exc:
        logger.exception(f"Unhandled exception in pipeline for Job {job_id}")
        db.rollback()
        job.status = "failed"
        job.error_message = str(exc)
        job.completed_at = datetime.utcnow()
        db.commit()
        return f"Job {job_id} failed: {str(exc)}"
    finally:
        db.close()
