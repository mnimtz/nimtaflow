import os
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from app.core.config import get_settings

settings = get_settings()


@worker_process_init.connect
def _flag_celery_worker(**_kwargs):
    """Mark every prefork CHILD as a worker. In a child, sys.argv is rewritten to
    ['-c', ...] (no 'celery'), so the argv sniff in _is_celery_worker() returned
    False and the children wrongly used the bounded pool — each keeping ~20 idle
    connections → the recurring 'too many clients already'. This env flag (read by
    _is_celery_worker) forces NullPool in the children, which closes its connection
    after every task. The worker-main and beat keep an intact argv, so the fallback
    still covers them; the web backend never fires this signal → bounded pool."""
    os.environ["PF_CELERY_WORKER"] = "1"

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
        # Video face detection is SLOW (ffmpeg frame sampling) — keep it on the
        # video queue (its own worker) so thousands of clips from the nightly sweep
        # don't starve the fast cpu queue (image faces, crop warming, thumbnails).
        # It needs the 1080p web MP4 anyway, which the video worker produces.
        "detect_video_faces": {"queue": "video"},  # video faces from 1080p frames
        "sweep_video_faces":  {"queue": "cpu"},     # light enqueuer, stays on cpu
        "warm_face_crops":    {"queue": "cpu"},   # pre-generate face-crop cache
        "verify_unnamed_faces": {"queue": "cpu"},  # nightly FP filter (re-detect crops)
        "reembed_imported":   {"queue": "cpu"},
        "retry_failed_ai":    {"queue": "cpu"},
        "retry_missing_thumbnails": {"queue": "cpu"},
        "backfill_xmp":       {"queue": "cpu"},   # one-off: stamp DB metadata into files
        "backfill_geo":       {"queue": "cpu"},   # offline reverse-geocode GPS → city
        # Dedicated queue + worker so slow video transcodes (esp. software h264)
        # never occupy the worker-cpu slots that make image thumbnails — those two
        # now run fully in parallel. worker-video has /dev/dri for QSV.
        "transcode_video":    {"queue": "video"},
        "mirror_originals":   {"queue": "cpu"},   # rclone one-way mirror of originals
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
    # Offsite mirror of the ORIGINAL photo/video files (rclone one-way sync with a
    # recoverable dated remote trash). Self-paced: hourly tick; the task only runs
    # when due per backup.mirror_schedule. Runs at 05:40, after the DB backup +
    # trash purge so deletions have already settled in the DB/library.
    "mirror-originals": {
        "task": "mirror_originals",
        "schedule": crontab(hour=5, minute=40),
    },
    # Nightly self-heal of the durable round-trip: stamp DB description/tags/rating
    # into any described photo that isn't in its file yet (xmp_sidecar_written not
    # True). Incremental + idempotent — closes gaps from any description that landed
    # while xmp.write_mode was off. 02:30, before the FP/video face sweeps.
    "backfill-xmp-nightly": {
        "task": "backfill_xmp",
        "schedule": crontab(hour=2, minute=30),
    },
    # Nightly offline reverse-geocoding: fill city/region for GPS photos that don't
    # have a place name yet (so the map's place search stays current as new geo
    # photos arrive). Idempotent, only touches photos missing a city. 04:45.
    "backfill-geo-nightly": {
        "task": "backfill_geo",
        "schedule": crontab(hour=4, minute=45),
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
    # Nightly trash retention: permanently delete photos that have been in the trash
    # longer than trash.retention_days (0 = keep forever). 05:15.
    "purge-trash-nightly": {
        "task": "purge_trash",
        "schedule": crontab(hour=5, minute=15),
    },
    # Nightly FULL face clustering — forms NEW people from the loose-face pool (the
    # 13k unassigned faces). Heavy HDBSCAN, so off-peak + on the CPU worker. 03:50.
    "cluster-faces-full-nightly": {
        "task": "cluster_faces_full",
        "schedule": crontab(hour=3, minute=50),
    },
    # Nightly: backfill ArcFace embeddings for imported (XMP-region) faces that have
    # none, so they become clusterable instead of stuck as 'unbekannt'. 03:10.
    "reembed-imported-nightly": {
        "task": "reembed_imported",
        "schedule": crontab(hour=3, minute=10),
    },
}
