from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Date, Text, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.timeutil import utcnow


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(String(256))
    birthdate: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    relationship_type: Mapped[Optional[str]] = mapped_column(String(64))
    # Contact details (optional) — shown on the person page.
    email: Mapped[Optional[str]] = mapped_column(String(256))
    phone: Mapped[Optional[str]] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(512))
    profile_face_id: Mapped[Optional[int]] = mapped_column(Integer)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    faces: Mapped[List["Face"]] = relationship("Face", back_populates="person")
