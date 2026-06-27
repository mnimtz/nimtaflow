"""A tiny job queue for OFFLOADED music generation to a remote worker (e.g. the
M3 Mac running stable-audio-open). The highlight render enqueues a job (prompt +
seconds), a remote worker claims it, generates the track and uploads the result.
The render waits briefly and falls back to the library / fal / no music if no
worker delivers in time — so a render never depends on the remote being up."""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Text, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class MusicJobStatus(str, enum.Enum):
    pending = "pending"
    claimed = "claimed"
    done = "done"
    error = "error"


class MusicJob(Base):
    __tablename__ = "music_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    seconds: Mapped[int] = mapped_column(Integer, default=40)
    status: Mapped[MusicJobStatus] = mapped_column(Enum(MusicJobStatus), default=MusicJobStatus.pending, index=True)
    result_path: Mapped[Optional[str]] = mapped_column(String(512))
    error: Mapped[Optional[str]] = mapped_column(String(512))
    worker: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
