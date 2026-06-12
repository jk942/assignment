from pydantic import BaseModel, Field
from datetime import date
from typing import Optional

class TransactionBase(BaseModel):
    txn_id: str
    date: date
    merchant: str
    amount: float
    currency: str
    status: str
    category: str
    account_id: str
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool = False

class TransactionCreate(TransactionBase):
    pass

class TransactionResponse(TransactionBase):
    id: str
    job_id: str
    llm_raw_response: Optional[str] = None

    class Config:
        from_attributes = True
