"""Public share links — token-based, login-free guest access to an album,
a single photo/video, or a trip (date range). Privacy-preserving by design:

- The token is a long unguessable random string; without it the share is invisible.
- A share can carry an optional password (hashed) and an optional expiry.
- `allow_download` gates access to the ORIGINAL files (previews always allowed).

Each public request re-validates token + expiry + (password) + that the requested
photo really belongs to the share, so a link can never be widened by guessing IDs.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ShareType(str, enum.Enum):
    album = "album"
    photo = "photo"
    trip = "trip"
    highlight = "highlight"


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    share_type: Mapped[ShareType] = mapped_column(Enum(ShareType), nullable=False)

    # exactly one of these is set, depending on share_type
    album_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("albums.id", ondelete="CASCADE"))
    photo_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("photos.id", ondelete="CASCADE"))
    highlight_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("highlights.id", ondelete="CASCADE"))
    # trip = an auto-detected event → stored as a date range + a title
    trip_from: Mapped[Optional[str]] = mapped_column(String(10))   # ISO date
    trip_to: Mapped[Optional[str]] = mapped_column(String(10))     # ISO date

    title: Mapped[Optional[str]] = mapped_column(String(256))
    password_hash: Mapped[Optional[str]] = mapped_column(String(256))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    allow_download: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    view_count: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def has_password(self) -> bool:
        return bool(self.password_hash)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        from datetime import timezone
        now = datetime.now(timezone.utc)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=timezone.utc)
        return now >= exp
