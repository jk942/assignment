from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Dict, Any
from app.schemas.transaction import TransactionResponse

class JobUploadResponse(BaseModel):
    job_id: str
    status: str

class LLMSummaryResponse(BaseModel):
    total_spend_by_currency: Dict[str, float]
    top_3_merchants: List[str]
    anomaly_count: int
    narrative: str
    risk_level: str

    class Config:
        from_attributes = True

class JobSummaryResponse(BaseModel):
    total_spend_inr: float
    total_spend_usd: float
    top_merchants: Any
    anomaly_count: int
    narrative: Optional[str] = None
    risk_level: Optional[str] = None

    class Config:
        from_attributes = True

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    summary: Optional[JobSummaryResponse] = None

class JobListItem(BaseModel):
    job_id: str
    filename: str
    status: str
    row_count: Optional[int] = None
    created_at: datetime

class JobResultsResponse(BaseModel):
    cleaned_transactions: List[TransactionResponse]
    flagged_anomalies: List[TransactionResponse]
    category_breakdown: Dict[str, int]
    llm_summary: Optional[LLMSummaryResponse] = None
