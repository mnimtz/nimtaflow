from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Album(Base):
    __tablename__ = "albums"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cover_photo_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("photos.id"))
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    photos: Mapped[List["AlbumPhoto"]] = relationship("AlbumPhoto", back_populates="album", cascade="all, delete-orphan")


class AlbumPhoto(Base):
    __tablename__ = "album_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    album_id: Mapped[int] = mapped_column(Integer, ForeignKey("albums.id"), nullable=False, index=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    album: Mapped["Album"] = relationship("Album", back_populates="photos")
    photo: Mapped["Photo"] = relationship("Photo", back_populates="album_entries")
