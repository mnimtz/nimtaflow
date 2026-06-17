from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "photoflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    # Two queues so slow GPU work never starves fast work:
    #   gpu → AI description/embedding + face detection (single-slot worker; the
    #         8 GB card holds exactly one VLM copy)
    #   cpu → scanning, thumbnails, clustering, metadata (parallel, no GPU)
    task_routes={
        "ai_photo":           {"queue": "gpu"},
        "process_photo":      {"queue": "cpu"},
        # Dedicated queue + worker so a scan indexes immediately instead of
        # queueing behind a long process_photo (thumbnail) backlog on "cpu".
        "scan_source":        {"queue": "scan"},
        "watch_sources":      {"queue": "cpu"},
        "auto_cluster_faces": {"queue": "cpu"},
        "write_person_name":  {"queue": "cpu"},
        "detect_faces_local": {"queue": "cpu"},   # server-side insightface (CPU)
        "sweep_faces_local":  {"queue": "cpu"},
        "reembed_imported":   {"queue": "cpu"},
        "transcode_video":    {"queue": "cpu"},   # worker-cpu has /dev/dri (QSV)
    },
)

# Periodic folder watching — check every minute which sources are due for a re-scan.
# The per-source interval (scan_interval_minutes) is honoured inside the task itself.
celery_app.conf.beat_schedule = {
    "watch-sources": {
        "task": "watch_sources",
        "schedule": 60.0,
    },
    # Auto-group unassigned faces so they don't pile up individually.
    "auto-cluster-faces": {
        "task": "auto_cluster_faces",
        "schedule": 300.0,
    },
    # Fallback for the remote-worker flow (re-queue locally if a worker vanished).
    "reclaim-ai": {
        "task": "reclaim_ai",
        "schedule": 120.0,
    },
    # Automatic backups — hourly tick; the task only runs when actually due.
    "scheduled-backup": {
        "task": "scheduled_backup",
        "schedule": 3600.0,
    },
}
