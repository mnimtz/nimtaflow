import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, DateTime, Integer, BigInteger, Float, Boolean, Text, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.core.timeutil import utcnow


class PhotoStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"
    skipped = "skipped"


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)  # videos exceed int4's 2.1 GB
    mime_type: Mapped[Optional[str]] = mapped_column(String(128))

    # ── Core EXIF ─────────────────────────────────────────────────────────────
    taken_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    taken_at_original: Mapped[Optional[str]] = mapped_column(String(32))
    timezone_offset: Mapped[Optional[str]] = mapped_column(String(8))
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    # Face-aware crop centre (0..1) so the grid doesn't cut off heads.
    focus_x: Mapped[Optional[float]] = mapped_column(Float)
    focus_y: Mapped[Optional[float]] = mapped_column(Float)
    # Tiny base64-JPEG placeholder (LQIP) shown instantly behind the grid tile while
    # the real thumbnail loads — the "instant scroll" feel (Immich/Google Photos).
    blur_data: Mapped[Optional[str]] = mapped_column(Text)
    # When a remote GPU worker has leased this photo's AI job (re-claimable if stale).
    ai_claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Bumped by a DB trigger on every UPDATE → drives iOS incremental /sync.
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
    orientation: Mapped[Optional[int]] = mapped_column(Integer)
    color_space: Mapped[Optional[str]] = mapped_column(String(32))

    # ── Camera & Optics ───────────────────────────────────────────────────────
    camera_make: Mapped[Optional[str]] = mapped_column(String(128))
    camera_model: Mapped[Optional[str]] = mapped_column(String(128))
    camera_serial: Mapped[Optional[str]] = mapped_column(String(128))
    lens_make: Mapped[Optional[str]] = mapped_column(String(128))
    lens_model: Mapped[Optional[str]] = mapped_column(String(256))
    focal_length: Mapped[Optional[float]] = mapped_column(Float)
    focal_length_35mm: Mapped[Optional[int]] = mapped_column(Integer)
    aperture: Mapped[Optional[float]] = mapped_column(Float)
    shutter_speed: Mapped[Optional[str]] = mapped_column(String(32))
    exposure_time: Mapped[Optional[float]] = mapped_column(Float)
    iso: Mapped[Optional[int]] = mapped_column(Integer)
    exposure_mode: Mapped[Optional[str]] = mapped_column(String(64))
    metering_mode: Mapped[Optional[int]] = mapped_column(Integer)
    white_balance: Mapped[Optional[int]] = mapped_column(Integer)
    flash: Mapped[Optional[int]] = mapped_column(Integer)
    software: Mapped[Optional[str]] = mapped_column(String(256))

    # ── GPS ───────────────────────────────────────────────────────────────────
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    altitude: Mapped[Optional[float]] = mapped_column(Float)
    gps_accuracy: Mapped[Optional[float]] = mapped_column(Float)
    location_name: Mapped[Optional[str]] = mapped_column(String(512))
    city: Mapped[Optional[str]] = mapped_column(String(256))
    country: Mapped[Optional[str]] = mapped_column(String(128))
    country_code: Mapped[Optional[str]] = mapped_column(String(4))

    # ── Copyright / IPTC / XMP ────────────────────────────────────────────────
    artist: Mapped[Optional[str]] = mapped_column(String(256))
    copyright: Mapped[Optional[str]] = mapped_column(String(512))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    caption: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)
    xmp_sidecar_written: Mapped[bool] = mapped_column(Boolean, default=False)
    xmp_sidecar_path: Mapped[Optional[str]] = mapped_column(String(2048))

    # ── AI ────────────────────────────────────────────────────────────────────
    description: Mapped[Optional[str]] = mapped_column(Text)
    description_language: Mapped[Optional[str]] = mapped_column(String(8))
    description_model: Mapped[Optional[str]] = mapped_column(String(128))
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768))        # jina-clip-v2 IMAGE vector (visual search)
    embedding_text: Mapped[Optional[List[float]]] = mapped_column(Vector(768))   # jina-clip-v2 vector of the description (semantic)

    # ── Processing ────────────────────────────────────────────────────────────
    status: Mapped[PhotoStatus] = mapped_column(Enum(PhotoStatus), default=PhotoStatus.pending, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    # AI step failed (e.g. provider 503) while the rest of processing succeeded —
    # lets us re-queue just-AI-failed photos without a full folder reprocess.
    ai_error: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # How many times AI processing has failed (e.g. Gemini outage). The retry
    # queue re-attempts ai_error photos until this hits a cap, so transient
    # provider outages don't permanently drop photos.
    ai_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Thumbnail attempts — so the reaper can retry thumbnail-less photos (e.g. a
    # stubborn TIFF a new fallback can now decode) yet cap genuinely-undecodable ones.
    thumb_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Thumbnails ────────────────────────────────────────────────────────────
    thumb_small: Mapped[Optional[str]] = mapped_column(String(512))
    thumb_medium: Mapped[Optional[str]] = mapped_column(String(512))
    thumb_large: Mapped[Optional[str]] = mapped_column(String(512))

    # ── Media type ────────────────────────────────────────────────────────────
    is_video: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    video_codec: Mapped[Optional[str]] = mapped_column(String(32))
    video_fps: Mapped[Optional[float]] = mapped_column(Float)
    video_bitrate: Mapped[Optional[int]] = mapped_column(Integer)
    video_webm_path: Mapped[Optional[str]] = mapped_column(String(512))
    # short animated hover preview (webp/gif), like a thumbnail for videos
    video_preview_path: Mapped[Optional[str]] = mapped_column(String(512))

    # ── User interaction ──────────────────────────────────────────────────────
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    trashed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # for retention auto-purge
    # Folder hidden from ALL display (gallery/search/people/highlights/map) via
    # display.hidden_folders. Face recognition still runs (workers ignore this flag),
    # so the person clustering benefits — the photos just never show. See access.py.
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # File no longer present on disk (detected during scan)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    missing_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    user_rating: Mapped[Optional[int]] = mapped_column(Integer)
    user_description: Mapped[Optional[str]] = mapped_column(Text)
    # Optional voice memo recorded by the user for this photo (cached audio file).
    voice_note_path: Mapped[Optional[str]] = mapped_column(String(512))
    # Person names read from the file's XMP:PersonInImage on import (comma-joined).
    # Lets a re-imported photo stay searchable by person + seeds face auto-assign.
    imported_person_names: Mapped[Optional[str]] = mapped_column(Text)
    # A face-detection pass has run (even if it found 0 faces). Stops a photo
    # described by a non-local provider (e.g. Gemini) from being claimed for a
    # faces-only pass forever when it genuinely has no faces.
    faces_scanned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # When the photo's MWG face regions (box + person name) were last written into the
    # file/sidecar. NULL = not yet written → the nightly backfill_faces task picks it up.
    faces_written_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    faces: Mapped[List["Face"]] = relationship("Face", back_populates="photo", cascade="all, delete-orphan")
    tags: Mapped[List["PhotoTag"]] = relationship("PhotoTag", back_populates="photo", cascade="all, delete-orphan")
    album_entries: Mapped[List["AlbumPhoto"]] = relationship("AlbumPhoto", back_populates="photo", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_photos_taken_at_id", "taken_at", "id"),
        Index("ix_photos_latitude_longitude", "latitude", "longitude"),
    )
