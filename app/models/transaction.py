import uuid
from sqlalchemy import Column, String, ForeignKey, Boolean, Numeric, Text, Date
from sqlalchemy.orm import relationship
from app.db.base import Base

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    txn_id = Column(String(100), nullable=False, index=True)
    date = Column(Date, nullable=False)
    merchant = Column(String(255), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(50), nullable=False)
    category = Column(String(100), nullable=False)
    account_id = Column(String(100), nullable=False, index=True)
    is_anomaly = Column(Boolean, nullable=False, default=False)
    anomaly_reason = Column(String(255), nullable=True)
    llm_category = Column(String(100), nullable=True)
    llm_raw_response = Column(Text, nullable=True)
    llm_failed = Column(Boolean, nullable=False, default=False)

    # Relationships
    job = relationship("Job", back_populates="transactions")
