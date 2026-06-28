import enum
from datetime import datetime
from typing import Optional, Any
from sqlalchemy import String, DateTime, Integer, Float, Text, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.core.timeutil import utcnow


class HighlightStatus(str, enum.Enum):
    pending = "pending"
    rendering = "rendering"
    done = "done"
    error = "error"


class Highlight(Base):
    """A rendered highlight/memory slideshow video built for a chosen "motto"."""
    __tablename__ = "highlights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(256))
    motto: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[HighlightStatus] = mapped_column(
        Enum(HighlightStatus), default=HighlightStatus.pending, index=True
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(1024))
    duration_sec: Mapped[Optional[float]] = mapped_column(Float)
    # Free-form parameters the render was built from (person_id, year, album_id, season …).
    params: Mapped[Optional[Any]] = mapped_column(JSON)
    # Number of photos that actually went into the slideshow (set after render).
    photo_count: Mapped[Optional[int]] = mapped_column(Integer)
    cover_photo_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("photos.id", ondelete="SET NULL")
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
