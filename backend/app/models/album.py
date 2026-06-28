import enum
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.timeutil import utcnow


class AlbumType(str, enum.Enum):
    manual = "manual"          # User curates manually
    smart = "smart"            # Rule-based (camera, date, person, tag, location...)
    ai = "ai"                  # Freetext AI prompt — AI decides which photos match


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    album_type: Mapped[AlbumType] = mapped_column(Enum(AlbumType), default=AlbumType.manual)
    cover_photo_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("photos.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Smart album rules (JSON dict with keys: date_from, date_to, cameras[], person_ids[], tags[], has_gps, media_type)
    smart_criteria: Mapped[Optional[Any]] = mapped_column(JSON)
    # AI album prompt (freetext, e.g. "beach photos with family")
    ai_prompt: Mapped[Optional[str]] = mapped_column(Text)
    # When AI album was last evaluated
    ai_last_evaluated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    photos: Mapped[List["AlbumPhoto"]] = relationship(
        "AlbumPhoto", back_populates="album", cascade="all, delete-orphan",
        order_by="AlbumPhoto.sort_order"
    )


class AlbumPhoto(Base):
    __tablename__ = "album_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(Integer, ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # For AI albums: confidence score (0-1)
    ai_score: Mapped[Optional[float]] = mapped_column()

    album: Mapped["Album"] = relationship("Album", back_populates="photos")
    photo: Mapped["Photo"] = relationship("Photo", back_populates="album_entries")
