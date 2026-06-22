from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Integer, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Face(Base):
    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(Integer, ForeignKey("photos.id"), nullable=False, index=True)
    person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("persons.id"), index=True)

    # Bounding box (0.0–1.0 relative)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_w: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_h: Mapped[float] = mapped_column(Float, nullable=False)

    confidence: Mapped[Optional[float]] = mapped_column(Float)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(512))
    detector: Mapped[Optional[str]] = mapped_column(String(64))
    # For video faces: the timestamp (seconds) of the frame the face was detected
    # in, so the crop is taken from THAT frame (not the 10%-mark thumbnail).
    frame_time: Mapped[Optional[float]] = mapped_column(Float)
    # Ignored/hidden face: excluded from the 'unbekannte Gesichter' list and from
    # clustering (for the many faces of strangers you don't want to manage).
    is_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # "Suggested match": ArcFace similarity to a named person in the borderline band
    # (below auto-assign, above noise). Stored so the user confirms with one tap.
    suggested_person_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("persons.id"), index=True)
    suggested_score: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    photo: Mapped["Photo"] = relationship("Photo", back_populates="faces")
    person: Mapped[Optional["Person"]] = relationship("Person", back_populates="faces")
