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
        "cluster_faces_full": {"queue": "cpu"},   # heavy manual 'Clustern' button → off the API process
        "detect_faces_local": {"queue": "cpu"},   # server-side insightface (CPU)
        "sweep_faces_local":  {"queue": "cpu"},
        # Video face detection is SLOW (ffmpeg frame sampling + insightface). It used
        # to share the `video` queue with transcodes on the single (-c 1) video worker,
        # so the nightly sweep's thousands of clips STARVED the 1080p transcode backlog
        # for days (vid_1080 didn't move). Moved to the `gpu` worker (idle — local VLM
        # disabled, AI is remote) so it runs in parallel, GPU-accelerated where present,
        # and never blocks transcodes again.
        "detect_video_faces": {"queue": "gpu"},  # video faces from 1080p frames (off the transcode worker)
        "sweep_video_faces":  {"queue": "cpu"},     # light enqueuer, stays on cpu
        "warm_face_crops":    {"queue": "cpu"},   # pre-generate face-crop cache
        "verify_unnamed_faces": {"queue": "cpu"},  # nightly FP filter (re-detect crops)
        "birthdate_sanity_faces": {"queue": "cpu"},  # v1.541: FP-cleanup vor Geburtsdatum
        "reembed_imported":   {"queue": "cpu"},
        "reingest_structured_descriptions": {"queue": "cpu"},  # v1.549
        "retry_failed_ai":    {"queue": "cpu"},
        "sweep_pending_video_ai": {"queue": "cpu"},  # self-heal videos stuck without description
        "sweep_websafe_videos":   {"queue": "cpu"},  # v1.538: promote H.264 8-bit videos ohne Transcode
        "retry_missing_thumbnails": {"queue": "cpu"},
        "backfill_xmp":       {"queue": "cpu"},   # one-off: stamp DB metadata into files
        "write_faces":        {"queue": "cpu"},   # MWG face regions (button + nightly incremental)
        "backfill_geo":       {"queue": "cpu"},   # offline reverse-geocode GPS → city
        # Fast EXIF date+GPS(+geocode) backfill straight from file headers. On the
        # SCAN queue (near-empty) so it does NOT wait behind the huge process_photo
        # cpu backlog — the map/timeline populate in minutes, not after the queue drains.
        "backfill_metadata":  {"queue": "scan"},
        "backfill_blur":      {"queue": "cpu"},   # tiny LQIP placeholders → instant scroll
        "suggest_faces":      {"queue": "scan"},  # borderline face→person suggestions
        # Dedicated queue + worker so slow video transcodes (esp. software h264)
        # never occupy the worker-cpu slots that make image thumbnails — those two
        # now run fully in parallel. worker-video has /dev/dri for QSV.
        "transcode_video":    {"queue": "video"},
        "sweep_missing_video_previews": {"queue": "video"},  # backfill hover-WebP für transkodierte Videos
        "mirror_originals":   {"queue": "cpu"},   # rclone one-way mirror of originals
        # Highlight slideshow rendering (ffmpeg xfade/concat from cached thumbs).
        # On the video queue/worker so a long render never blocks the fast cpu work.
        "render_highlight":   {"queue": "video"},
        "animate_photo":      {"queue": "video"},  # external video-AI (Veo) image→clip
        "generate_weekly_highlight": {"queue": "cpu"},  # light: creates a Highlight + dispatches render
        "reap_stuck_highlights": {"queue": "cpu"},  # self-heal jobs killed mid-render
        "reap_stuck_photos":  {"queue": "cpu"},   # self-heal photos stuck in 'processing'
        "apply_hidden_folders": {"queue": "cpu"}, # sync Photo.is_hidden to the setting
        "firetv_auto_update":   {"queue": "cpu"}, # täglich APK-Update via GitHub
    },
)

# Periodic folder watching — check every minute which sources are due for a re-scan.
# The per-source interval (scan_interval_minutes) is honoured inside the task itself.
celery_app.conf.beat_schedule = {
    # Every 5 min (was 60s): on a busy box a watch_sources run can take longer than
    # its interval, so a 60s cadence let thousands pile up on the cpu queue. The
    # per-source scan_interval_minutes still governs when a source is actually due.
    "watch-sources": {
        "task": "watch_sources",
        "schedule": 300.0,
    },
    # XMP-Repair-Watchdog: startet die xmp_repair_queue-Abarbeitung immer
    # wieder neu, wenn noch pending Zeilen da sind aber gerade kein Worker
    # läuft. Verhindert dass ein Deploy/Crash den Repair für Stunden
    # unterbrechen kann - alle 5 min wird wieder aufgeholt.
    "xmp-repair-watchdog": {
        "task": "xmp_repair_watchdog",
        "schedule": 300.0,
    },
    # Self-heal photos orphaned at status=processing by a deploy/restart (see task).
    "reap-stuck-photos": {
        "task": "reap_stuck_photos",
        "schedule": 600.0,
    },
    # Grow existing people from loose faces (light, grow_only). New-cluster forming
    # (heavy HDBSCAN) is manual-only. Every 10 min keeps it gentle on the server.
    "auto-cluster-faces": {
        "task": "auto_cluster_faces",
        "schedule": 600.0,
    },
    # v1.538: alle 30 Min die verbleibenden Videos gegen die Web-Safe-Regel
    # scannen — spart massenhaft Transcodes für schon fertige H.264-Videos.
    "websafe-video-sweep": {
        "task": "sweep_websafe_videos",
        "schedule": 1800.0,
    },
    # Face-Vorschläge — vorher gab es KEINEN Beat-Schedule, deshalb waren bei einem
    # User 62 k Faces (47 %) weder assigned noch mit Suggestion versehen. Läuft
    # täglich 04:15 UTC (nach dem 03:50 UTC Cluster-Full und vor dem 07:00 UTC
    # Wochen-Highlight), damit alle neu detektierten und alle nicht-zugeordneten
    # Faces regelmäßig Kandidaten pro Person bekommen.
    "suggest-faces-daily": {
        "task": "suggest_faces",
        "schedule": crontab(hour=4, minute=15),
    },
    # v1.541: alle 6 h False-Positives entfernen die vor der Geburt der Person
    # datiert sind (die Grow-Phase kann das gelegentlich produzieren).
    "birthdate-sanity-6h": {
        "task": "birthdate_sanity_faces",
        "schedule": 21600.0,
    },
    # "Highlight der Woche" — täglich 07:00 UTC prüfen, ob für die AKTUELLE ISO-Woche
    # noch keins existiert. Sonst würde ein Server-Ausfall am Montag 07:00 die ganze
    # Woche ohne Highlight lassen (siehe KW 26/27 in Prod: mussten manuell nachgeholt
    # werden, weil der Montags-Cron nicht traf). Der Task selbst hat idempotenten
    # Dedup gegen doppelte Erstellung.
    "weekly-highlight": {
        "task": "generate_weekly_highlight",
        "schedule": crontab(hour=7, minute=0),
    },
    # Self-heal highlights stuck in "rendering" (worker killed mid-task, e.g. deploy).
    "reap-stuck-highlights": {
        "task": "reap_stuck_highlights",
        "schedule": 900.0,
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
    # Backfill animated hover-WebP for videos that have a webm but no preview.
    "sweep-missing-video-previews": {
        "task": "sweep_missing_video_previews",
        "schedule": 300.0,
    },
    # Sweep for videos stuck without description: no webm → transcode; has webm → reclaim.
    "sweep-pending-video-ai": {
        "task": "sweep_pending_video_ai",
        "schedule": 600.0,
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
    # Nightly, incremental, capped: write MWG face regions (person names + boxes) into
    # files for photos that don't have them yet — works through the library „nach und
    # nach" (3000/Nacht) instead of redoing everything. Replaces the need for
    # scan.force_reindex for person-name persistence.
    "backfill-faces-nightly": {
        "task": "write_faces",
        "schedule": crontab(hour=3, minute=10),
        "kwargs": {"incremental": True, "limit": 3000},
    },
    # Nightly fast EXIF date+GPS backfill (scan queue) so newly-imported photos get
    # their date/coordinates within the night even when the process_photo cpu backlog
    # is deep. Runs BEFORE geo so the geocoder then has fresh coordinates. 04:30.
    "backfill-metadata-nightly": {
        "task": "backfill_metadata",
        "schedule": crontab(hour=4, minute=30),
    },
    # Nightly offline reverse-geocoding: fill city/region for GPS photos that don't
    # have a place name yet (so the map's place search stays current as new geo
    # photos arrive). Idempotent, only touches photos missing a city. 04:45.
    "backfill-geo-nightly": {
        "task": "backfill_geo",
        "schedule": crontab(hour=4, minute=45),
    },
    # Nightly LQIP backfill: tiny blur placeholders for existing photos that don't
    # have one yet (instant-scroll grid). Cheap, reads the small thumb. 05:05.
    "backfill-blur-nightly": {
        "task": "backfill_blur",
        "schedule": crontab(hour=5, minute=5),
        "kwargs": {"limit": 8000},
    },
    # Nightly false-positive face filter: re-detect unnamed faces' crops, ignore
    # the ones that aren't faces (hands/patterns). New photos keep arriving, so it
    # runs every night at 03:30 to keep the People grid clean.
    "verify-unnamed-faces": {
        "task": "verify_unnamed_faces",
        "schedule": crontab(hour=3, minute=30),
    },
    # Video face detection: alle 4h statt nur nightly, damit neue Transcode-Videos
    # nicht bis zum nächsten Morgen auf ihren Gesichts-Scan warten.
    "sweep-video-faces": {
        "task": "sweep_video_faces",
        "schedule": 14400.0,  # alle 4 Stunden
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
    # Täglich 06:05: FireTV APK Auto-Update — prüft ob ein neueres 'firetv-latest'
    # GitHub-Release vorliegt und lädt es. No-op wenn software.firetv_auto_update != true.
    "firetv-auto-update": {
        "task": "firetv_auto_update",
        "schedule": crontab(hour=6, minute=5),
        "options": {"queue": "cpu"},
    },
}
