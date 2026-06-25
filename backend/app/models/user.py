import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Enum, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.timeutil import utcnow


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Self-service profile
    birthdate: Mapped[Optional[str]] = mapped_column(String(32))    # ISO "YYYY-MM-DD"
    avatar_path: Mapped[Optional[str]] = mapped_column(String(512))
    person_id: Mapped[Optional[int]] = mapped_column(Integer)       # "this is me" → Person link

    # NimtaFlow Pro (Server-Entitlement: per Schlüssel eingelöst oder Admin gesetzt).
    # App-Store-Käufe schalten Pro zusätzlich on-device via StoreKit frei.
    is_pro: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_source: Mapped[Optional[str]] = mapped_column(String(32))   # "key" | "admin" | "iap"

    # 2FA
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Per-user access restrictions (JSON)
    # { visible_from: "2020-01-01", visible_until: null,
    #   folder_whitelist: [], folder_blacklist: [],
    #   visible_person_ids: null,  (null = all)
    #   allow_map: true, allow_download: true, allow_share: true,
    #   allow_pipeline: false }
    access_config: Mapped[Optional[dict]] = mapped_column(JSON)

    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
