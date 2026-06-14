import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Float, Text, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(256))

    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)

    api_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    speed_per_min: Mapped[Optional[float]] = mapped_column(Float)

    config: Mapped[Optional[dict]] = mapped_column(JSON)  # snapshot of settings at job start

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False, index=True)
    photo_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("photos.id"), index=True)

    level: Mapped[str] = mapped_column(String(16), default="INFO")  # DEBUG, INFO, WARNING, ERROR
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON)

    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    ai_provider: Mapped[Optional[str]] = mapped_column(String(64))
    api_cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
