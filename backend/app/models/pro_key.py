"""Redeemable NimtaFlow Pro license keys.

For gifting / self-hoster family access WITHOUT going through Apple IAP: an admin
generates keys; a user redeems one and their account becomes Pro (is_pro=True).
App Store purchases unlock Pro on-device via StoreKit independently of this.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


class ProKey(Base):
    __tablename__ = "pro_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(256))         # e.g. "Familie Oma"
    used_by_user_id: Mapped[Optional[int]] = mapped_column(Integer)  # null = noch frei
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
