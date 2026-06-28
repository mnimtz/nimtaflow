#!/usr/bin/env python3
"""PhotoFlow M3 video worker — pulls local AI-video jobs and renders them on the Mac.

Architecture (matches the "M3 produces when online + buffer" idea):
  • Polls  GET  {BASE}/api/remote/video-jobs/next          (X-Remote-Token)
  • Fetch  GET  {BASE}/api/remote/image/{photo_id}         (source still = thumb_large)
  • Render locally  →  MP4
  • Upload POST {BASE}/api/remote/video-jobs/{id}/complete (multipart 'file')
  • On error POST {BASE}/api/remote/video-jobs/{id}/fail

Runs intermittently (launchd, like com.photoflow.m3video). If the Mac is off, jobs
just wait in the queue. Decoupled from request timing entirely.

Setup:
  export PHOTOFLOW_BASE=http://your-server:8090
  export PHOTOFLOW_REMOTE_TOKEN=…           (same token as start_m3_video.sh)
  pip install requests                       # ffmpeg must be on PATH
  python3 scripts/m3_ltx_worker.py

RENDERER: ships with a free ffmpeg Ken-Burns fallback so the whole pipeline is
testable TODAY without any model. Swap `render_clip` for the LTX-2.3 (MLX) call when
the model is installed — that's the only line that changes (see TODO below).
"""
import os
import re
import sys
import time
import tempfile
import subprocess

try:
    import requests
except ImportError:
    sys.exit("Bitte 'pip install requests' (im M3-Worker-venv).")

BASE = os.environ.get("PHOTOFLOW_BASE", "http://your-server:8090").rstrip("/")
TOKEN = os.environ.get("PHOTOFLOW_REMOTE_TOKEN", "")
POLL_SECONDS = int(os.environ.get("PHOTOFLOW_POLL", "30"))
# SAFETY: only render when at least this much memory is reclaimable. Highlights are
# not time-critical, so when the M3 is busy with describe/video we simply WAIT — never
# render under pressure, never crash the box or the other workers. "Slow is fine."
MIN_FREE_GB = float(os.environ.get("PHOTOFLOW_MIN_FREE_GB", "24"))
H = {"X-Remote-Token": TOKEN}


def _available_gb() -> float:
    """Reclaimable memory on macOS ≈ free + inactive + speculative + purgeable pages.
    (macOS keeps 'free' low by design — those other buckets are reclaimable.)"""
    try:
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True).stdout
        page = int(re.search(r"page size of (\d+) bytes", out).group(1))
        def pages(name):
            m = re.search(rf"{name}:\s+(\d+)", out)
            return int(m.group(1)) if m else 0
        reclaimable = (pages("Pages free") + pages("Pages inactive")
                       + pages("Pages speculative") + pages("Pages purgeable"))
        return reclaimable * page / 1024 / 1024 / 1024
    except Exception:
        return 0.0  # unknown → treat as "no headroom" (safe: we wait)


def _has_headroom() -> bool:
    avail = _available_gb()
    ok = avail >= MIN_FREE_GB
    if not ok:
        print(f"warte: nur {avail:.0f} GB frei (brauche ≥ {MIN_FREE_GB:.0f}) — andere Worker aktiv", flush=True)
    return ok


def render_clip(image_path: str, prompt: str, seconds: int, out_path: str) -> None:
    """Produce `out_path` (MP4) from a still image.

    ── TODO: LTX-2.3 (MLX) integration point ──────────────────────────────────
    Replace the ffmpeg block below with a call to the local LTX model, e.g. via
    dgrauet/ltx-2-mlx or the james-see/ltx-video-mac CLI:
        subprocess.run(["ltx-mlx", "i2v", "--image", image_path,
                        "--prompt", prompt, "--seconds", str(seconds),
                        "--out", out_path], check=True)
    The prompt already includes the creative scene (e.g. "… durch eine Unterwasser-
    welt …") plus an identity-consistency hint, set server-side.
    ───────────────────────────────────────────────────────────────────────────

    FALLBACK (works now, no model): a gentle Ken-Burns zoom so the queue is testable.
    """
    fps = 30
    frames = max(1, int(seconds * fps))
    vf = (f"scale=1280:720:force_original_aspect_ratio=increase,"
          f"crop=1280:720,zoompan=z='min(zoom+0.0010,1.15)':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1280x720:fps={fps},format=yuv420p")
    subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", image_path, "-t", str(seconds),
         "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         out_path],
        check=True, capture_output=True,
    )


def process(job: dict) -> None:
    jid, pid = job["id"], job["photo_id"]
    prompt, seconds = job.get("prompt", ""), int(job.get("seconds", 4))
    print(f"[job {jid}] photo={pid} seconds={seconds} prompt={prompt[:60]!r}", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        img = os.path.join(tmp, "src.jpg")
        out = os.path.join(tmp, "out.mp4")
        r = requests.get(f"{BASE}/api/remote/image/{pid}", headers=H, timeout=30)
        r.raise_for_status()
        with open(img, "wb") as f:
            f.write(r.content)
        try:
            render_clip(img, prompt, seconds, out)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode()[-300:]
            requests.post(f"{BASE}/api/remote/video-jobs/{jid}/fail",
                          headers=H, params={"error": f"render: {err}"}, timeout=30)
            print(f"[job {jid}] render failed", flush=True)
            return
        with open(out, "rb") as f:
            up = requests.post(f"{BASE}/api/remote/video-jobs/{jid}/complete",
                               headers=H, files={"file": ("clip.mp4", f, "video/mp4")}, timeout=120)
        up.raise_for_status()
        print(f"[job {jid}] done", flush=True)


def main() -> None:
    if not TOKEN:
        sys.exit("PHOTOFLOW_REMOTE_TOKEN fehlt.")
    print(f"M3 LTX worker → {BASE} (poll {POLL_SECONDS}s, min frei {MIN_FREE_GB:.0f} GB)", flush=True)
    while True:
        try:
            # Don't even CLAIM a job unless we can render it safely right now — otherwise
            # a claimed job would sit stuck in "rendering" while we wait for memory.
            if _has_headroom():
                r = requests.get(f"{BASE}/api/remote/video-jobs/next", headers=H, timeout=30)
                r.raise_for_status()
                job = (r.json() or {}).get("job")
                if job:
                    process(job)
                    continue  # drain queue without waiting
        except Exception as e:
            print(f"poll error: {e}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
