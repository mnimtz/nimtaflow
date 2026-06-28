from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.timeutil import utcnow


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
    # Upload-Phase 3: a non-admin may manage their OWN sources (folders within their
    # allowed scope). null = global/admin source. Plain Integer (no FK — a 2nd FK path
    # onto users has bitten the mapper before); ownership is enforced in the router.
    owner_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Folder watching: re-scan every N minutes (0 = manual only)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Detect & flag files removed from disk on each scan
    detect_deletions: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-folder AI provider override: null = use global, 'off' = no AI,
    # else 'gemini' | 'local' | 'ollama'.
    ai_provider: Mapped[Optional[str]] = mapped_column(String(32))

    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_scan_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
