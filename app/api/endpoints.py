import os
import uuid
import shutil
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db

# CRITICAL FIX: Removed global model imports from here to prevent the circular dependency loop.
from app.schemas.job import (
    JobUploadResponse,
    JobStatusResponse,
    JobResultsResponse,
    JobListItem,
    JobSummaryResponse
)
from app.core.config import settings
from app.tasks.pipeline_tasks import process_transaction_file

router = APIRouter()

@router.post(
    "/jobs/upload",
    response_model=JobUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload transaction CSV file"
)
async def upload_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Safe Import inside the function execution block
    from app.models.job import Job

    # 1. Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file extension. Only CSV files are allowed."
        )

    # 2. Reject empty files (check size or content length if available, or read first chunk)
    # Let's read first few bytes to check if empty
    first_bytes = await file.read(100)
    if not first_bytes.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file. Please upload a valid CSV file with transaction records."
        )
    # Seek back to the beginning of the file
    await file.seek(0)

    # 3. Create Job record
    job_id = str(uuid.uuid4())
    db_job = Job(
        id=job_id,
        filename=filename,
        status="pending"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)

    # 4. Save uploaded file to the uploads directory
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{job_id}.csv")
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # Update status to failed
        db_job.status = "failed"
        db_job.error_message = f"Failed to save file: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save uploaded file: {str(e)}"
        )

    # 5. Enqueue Celery task
    try:
        process_transaction_file.delay(job_id)
    except Exception as e:
        # Log error but don't crash, the status will show failed or celery will pick up eventually
        # If redis/celery is down, let's report it
        db_job.status = "failed"
        db_job.error_message = f"Failed to queue celery task: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue background processing task: {str(e)}"
        )

    return JobUploadResponse(job_id=job_id, status="pending")


@router.get(
    "/jobs/{job_id}/status",
    response_model=JobStatusResponse,
    summary="Get job processing status"
)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    # Safe Import inside the function execution block
    from app.models.job import Job

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found."
        )

    summary_response = None
    if job.status == "completed" and job.summary:
        summary_response = JobSummaryResponse(
            total_spend_inr=float(job.summary.total_spend_inr),
            total_spend_usd=float(job.summary.total_spend_usd),
            top_merchants=job.summary.top_merchants,
            anomaly_count=job.summary.anomaly_count,
            narrative=job.summary.narrative,
            risk_level=job.summary.risk_level
        )

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        summary=summary_response
    )


@router.get(
    "/jobs/{job_id}/results",
    response_model=JobResultsResponse,
    summary="Get job processing results"
)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    # Safe Imports inside the function execution block
    from app.models.job import Job
    from app.models.transaction import Transaction

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found."
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job {job_id} is in '{job.status}' status. Results are only available for 'completed' jobs."
        )

    # Fetch transactions
    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()

    # Split into cleaned and anomalies
    cleaned_transactions = [t for t in transactions if not t.is_anomaly]
    flagged_anomalies = [t for t in transactions if t.is_anomaly]

    # Category breakdown (using all transactions)
    category_breakdown = {}
    for t in transactions:
        category_breakdown[t.category] = category_breakdown.get(t.category, 0) + 1

    llm_summary = None
    if job.summary:
        llm_summary = {
            "total_spend_by_currency": {
                "INR": float(job.summary.total_spend_inr),
                "USD": float(job.summary.total_spend_usd)
            },
            "top_3_merchants": [merchant["merchant"] for merchant in job.summary.top_merchants],
            "anomaly_count": job.summary.anomaly_count,
            "narrative": job.summary.narrative,
            "risk_level": job.summary.risk_level
        }

    return JobResultsResponse(
        cleaned_transactions=cleaned_transactions,
        flagged_anomalies=flagged_anomalies,
        category_breakdown=category_breakdown,
        llm_summary=llm_summary
    )


@router.get(
    "/jobs",
    response_model=List[JobListItem],
    summary="List all jobs"
)
def list_jobs(
    status: Optional[str] = Query(None, description="Filter jobs by status"),
    db: Session = Depends(get_db)
):
    # Safe Import inside the function execution block
    from app.models.job import Job

    query = db.query(Job)
    if status:
        query = query.filter(func.lower(Job.status) == status.strip().lower())

    jobs = query.order_by(Job.created_at.desc()).all()

    result = []
    for job in jobs:
        # Use clean row count if completed, otherwise raw count (or None)
        row_count = job.row_count_clean if job.status == "completed" else job.row_count_raw
        result.append(
            JobListItem(
                job_id=job.id,
                filename=job.filename,
                status=job.status,
                row_count=row_count,
                created_at=job.created_at
            )
        )

    return result