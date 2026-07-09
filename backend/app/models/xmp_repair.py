"""Persistente XMP-Repair-Queue.

Zweck: der große "Backfill Sidecar + EXIF-Embed" muss über 100k Fotos
zuverlässig durchlaufen, auch wenn zwischendurch Deploys/Restarts kommen.
Bisheriges Design: In-Memory-Liste im Celery-Task → Restart = Fortschritt weg.

Neu: jede Photo-ID ist eine Zeile in dieser Tabelle. Nach jedem
erfolgreichen Schreiben wird die Zeile SOFORT auf status='done' gesetzt +
committed. Bei Restart holt der Task nur noch die 'pending'-Zeilen.

Zusätzlich: post-verify. Nach exiftool wird die Datei nochmal gelesen
und der Description-String gesucht. Ist er NICHT drin → status='failed'
mit Fehlermeldung — das war der bisherige Blindspot (DB-Flag=true, aber
Datei physisch leer)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class XmpRepairItem(Base):
    __tablename__ = "xmp_repair_queue"

    # photo_id ist der PK — jedes Foto max EINE Zeile in der Queue.
    photo_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Status-Machine: pending -> in_progress -> done | failed | skipped
    #   pending      = wartet auf Bearbeitung
    #   in_progress  = wird gerade bearbeitet (mit locked_at markiert)
    #   done         = Sidecar UND Embed verified
    #   failed       = alle attempts aufgebraucht
    #   skipped      = Datei fehlt / read-only / nicht schreibbar
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)

    # Retry-Zähler, gedeckelt bei ~5 damit permanente Fails nicht ewig loopen
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Der Grund warum das Foto in der Queue landete - informativ.
    #   sidecar_missing | sidecar_stale | embed_missing | manual
    reason: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")

    # Zeitstempel des letzten Lease (in_progress). Stale-Detection: > 10 min
    # ohne Status-Update -> Zeile ist verwaist und darf reclaimed werden.
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[Optional[str]] = mapped_column(String(64))  # celery worker id

    # Fehlermeldung des letzten Versuchs
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_xmp_repair_status_photo", "status", "photo_id"),
    )
