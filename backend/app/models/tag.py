from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Integer, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)

    photo_tags: Mapped[List["PhotoTag"]] = relationship("PhotoTag", back_populates="tag")


class PhotoTag(Base):
    __tablename__ = "photo_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id"), nullable=False, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(32))  # ai, manual

    photo: Mapped["Photo"] = relationship("Photo", back_populates="tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="photo_tags")
