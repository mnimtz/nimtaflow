from celery import Celery
from celery.schedules import crontab
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
        "detect_faces_local": {"queue": "cpu"},   # server-side insightface (CPU)
        "sweep_faces_local":  {"queue": "cpu"},
        "detect_video_faces": {"queue": "cpu"},   # video faces from 1080p frames
        "sweep_video_faces":  {"queue": "cpu"},
        "warm_face_crops":    {"queue": "cpu"},   # pre-generate face-crop cache
        "verify_unnamed_faces": {"queue": "cpu"},  # nightly FP filter (re-detect crops)
        "reembed_imported":   {"queue": "cpu"},
        "retry_failed_ai":    {"queue": "cpu"},
        "retry_missing_thumbnails": {"queue": "cpu"},
        # Dedicated queue + worker so slow video transcodes (esp. software h264)
        # never occupy the worker-cpu slots that make image thumbnails — those two
        # now run fully in parallel. worker-video has /dev/dri for QSV.
        "transcode_video":    {"queue": "video"},
    },
)

# Periodic folder watching — check every minute which sources are due for a re-scan.
# The per-source interval (scan_interval_minutes) is honoured inside the task itself.
celery_app.conf.beat_schedule = {
    "watch-sources": {
        "task": "watch_sources",
        "schedule": 60.0,
    },
    # Grow existing people from loose faces (light, grow_only). New-cluster forming
    # (heavy HDBSCAN) is manual-only. Every 10 min keeps it gentle on the server.
    "auto-cluster-faces": {
        "task": "auto_cluster_faces",
        "schedule": 600.0,
    },
    # Retry queue: re-attempt AI that failed (e.g. a Gemini outage) every 15 min.
    "retry-failed-ai": {
        "task": "retry_failed_ai",
        "schedule": 900.0,
    },
    # Self-heal thumbnail gaps (re-try attempted-but-failed thumbnails, capped).
    "retry-missing-thumbnails": {
        "task": "retry_missing_thumbnails",
        "schedule": 600.0,
    },
    # Self-heal face gaps: enqueue local face detection for images still lacking a
    # face pass, INDEPENDENT of the (slow) description backlog. Without this on the
    # schedule, undescribed images never got a local face pass — their faces sat
    # stuck for as long as descriptions lagged (days). Every 10 min.
    "sweep-faces-local": {
        "task": "sweep_faces_local",
        "schedule": 600.0,
    },
    # Keep the face-crop cache (SSD) warm so the People page never crops on-demand
    # (the slow/black-tile case). This was a button-only task and never ran on its
    # own, so new faces — and faces whose person_id changed on re-clustering — had
    # no cached crop. Idempotent (only generates genuine misses). Every 30 min.
    "warm-face-crops": {
        "task": "warm_face_crops",
        "schedule": 1800.0,
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
    # Nightly false-positive face filter: re-detect unnamed faces' crops, ignore
    # the ones that aren't faces (hands/patterns). New photos keep arriving, so it
    # runs every night at 03:30 to keep the People grid clean.
    "verify-unnamed-faces": {
        "task": "verify_unnamed_faces",
        "schedule": crontab(hour=3, minute=30),
    },
    # Nightly video face detection (videos that gained a 1080p web version that day).
    "sweep-video-faces": {
        "task": "sweep_video_faces",
        "schedule": crontab(hour=4, minute=0),
    },
}
