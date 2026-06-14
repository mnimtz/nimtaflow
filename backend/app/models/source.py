from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PhotoSource(Base):
    __tablename__ = "photo_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(256))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    watch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recursive: Mapped[bool] = mapped_column(Boolean, default=True)
    exclusion_patterns: Mapped[Optional[str]] = mapped_column(String(1024))  # comma-separated
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_scan_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
