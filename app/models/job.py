import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Numeric, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    row_count_raw = Column(Integer, nullable=True)
    row_count_clean = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    transactions = relationship("Transaction", back_populates="job", cascade="all, delete-orphan")
    summary = relationship("JobSummary", back_populates="job", uselist=False, cascade="all, delete-orphan")


class JobSummary(Base):
    __tablename__ = "job_summaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    total_spend_inr = Column(Numeric(15, 2), nullable=False, default=0.0)
    total_spend_usd = Column(Numeric(15, 2), nullable=False, default=0.0)
    top_merchants = Column(JSON, nullable=False)  # stores top merchants list/dict

    anomaly_count = Column(Integer, nullable=False, default=0)
    narrative = Column(Text, nullable=False)
    risk_level = Column(String(50), nullable=False)  # low, medium, high

    # Relationships
    job = relationship("Job", back_populates="summary")
