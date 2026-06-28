"""PhotoFlow remote GPU worker (pull-agent).

Runs the SAME PhotoFlow image on a machine that has a good GPU, pointed at a
remote PhotoFlow server. It polls for AI jobs, downloads only the JPEG over
HTTP, runs the local VLM + face detection + embedding on the GPU, and posts the
result back as JSON. No DB, no shared storage, no file access — fully generic.

Run:  python -m app.remote_worker.agent
Env:  PHOTOFLOW_SERVER (e.g. http://your-server:8090)
      PHOTOFLOW_REMOTE_TOKEN  (must match Settings → Remote-Worker)
      WORKER_NAME (optional, defaults to hostname)
      POLL_INTERVAL (seconds, default 5)
"""
import asyncio
import io
import os
import socket
import time

import httpx
from PIL import Image

SERVER = os.getenv("PHOTOFLOW_SERVER", "http://localhost:8090").rstrip("/")
TOKEN = os.getenv("PHOTOFLOW_REMOTE_TOKEN", "")
NAME = os.getenv("WORKER_NAME") or socket.gethostname()
POLL = float(os.getenv("POLL_INTERVAL", "5"))
MODE = (os.getenv("WORKER_MODE") or "all").strip().lower()  # all | faces | describe | embed
MEDIA = (os.getenv("WORKER_MEDIA") or "both").strip().lower()  # both | images | videos
# Describe backend: "local" = bundled Qwen/Florence (needs torch); "ollama" = a
# co-located Ollama server (e.g. on a Mac via Metal — model chosen PER WORKER).
BACKEND = (os.getenv("WORKER_BACKEND") or "local").strip().lower()
OLLAMA_URL = (os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "qwen2.5vl:7b"
HEAD = {"X-Remote-Token": TOKEN}

# Is InsightFace importable here? A describe-only Mac worker won't have it — then
# we never claim/mark faces (the dedicated faces worker handles them).
try:
    from app.services import face_detect_insightface as _fi  # noqa: F401
    FACES_AVAILABLE = True
except Exception:
    FACES_AVAILABLE = False


def _dedup_faces(raw: list) -> list:
    """Collapse the same person seen across many video frames into one entry.
    Greedy by confidence: a face is dropped if it matches an already-kept face
    (cosine similarity > 0.5 on the embedding)."""
    import math

    def cos(a, b):
        if not a or not b:
            return 0.0
        na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(x * x for x in b))
        return (sum(x * y for x, y in zip(a, b)) / (na * nb)) if na and nb else 0.0

    reps = []
    for f in sorted(raw, key=lambda x: x.get("confidence", 0) or 0, reverse=True):
        emb = f.get("embedding")
        if emb and any(cos(emb, r.get("embedding")) > 0.5 for r in reps):
            continue
        reps.append(f)
    return reps


async def _process(client: httpx.AsyncClient, job: dict) -> str:
    t0 = time.time()
    pid = job["photo_id"]
    r = await client.get(SERVER + job["image_url"], headers=HEAD, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")

    # Video: fetch the evenly-sampled frames so Qwen sees the whole clip, not
    # just the 10%-mark thumbnail. Falls back to the single frame if none load.
    frames = None
    furls = job.get("frame_urls") or []
    if furls:
        frames = []
        for fu in furls:
            try:
                fr = await client.get(SERVER + fu, headers=HEAD, timeout=60)
                if fr.status_code == 200 and fr.content:
                    frames.append(Image.open(io.BytesIO(fr.content)).convert("RGB"))
            except Exception as e:
                print(f"[agent] frame fetch failed {fu}: {type(e).__name__}")
        if frames:
            print(f"[agent] #{pid} video: {len(frames)} frames")
        else:
            frames = None

    # Describe backend chosen per worker: bundled local VLM, or a co-located Ollama
    # (the model lives on the worker via OLLAMA_MODEL, so different Macs can run
    # different models simultaneously — the server records which one per photo).
    if BACKEND == "ollama":
        from app.services.ai.ollama import OllamaProvider
        prov = OllamaProvider(OLLAMA_URL, OLLAMA_MODEL)
    else:
        from app.services.ai.local_vlm import LocalVLMProvider
        prov = LocalVLMProvider(job.get("model", "florence2-base"))
    lang = job.get("language", "de")
    prompt = job.get("prompt")

    # faces_only: the photo already has an (imported) description — only run face
    # detection, don't re-describe/re-tag.
    faces_only = bool(job.get("faces_only"))
    if faces_only:
        desc, tags = None, []
    else:
        desc = await prov.describe_image(img, lang, prompt, frames=frames)
        tags = await prov.generate_tags(img, lang, job.get("tag_prompt"), caption=desc) if desc else []
    # Embeddings are computed CENTRALLY on the server (one vector space across all
    # workers/models) — the agent no longer embeds.

    faces_enabled = bool(job.get("faces_enabled", True))
    faces = []
    # A describe-only worker (e.g. the Mac) NEVER touches faces → leave faces_scanned
    # False so the dedicated faces worker (Asus) still claims the photo.
    if MODE == "describe":
        faces_done = False
    else:
        faces_done = not faces_enabled  # nothing to do → already "done"
    if faces_enabled and FACES_AVAILABLE and MODE != "describe":
        try:
            from app.services import face_detect_insightface as fi
            if fi.available():
                faces_done = True
                min_px = float(job.get("min_face_px", 0) or 0)
                min_conf = float(job.get("min_conf", 0.5) or 0.5)
                # Video: detect across frames sampled over the whole clip; carry
                # each frame's TIMESTAMP so the server can later crop the face from
                # exactly that frame. Then dedup so the same person across frames
                # collapses to one entry (per unique person), keeping its timestamp.
                # [(image, frame_time_or_None)]
                face_imgs = [(img, None)]
                fframes = job.get("face_frames") or []
                if fframes:
                    fetched = []
                    for ff in fframes:
                        try:
                            fr = await client.get(SERVER + ff["url"], headers=HEAD, timeout=60)
                            if fr.status_code == 200 and fr.content:
                                fetched.append((Image.open(io.BytesIO(fr.content)).convert("RGB"), ff.get("t")))
                        except Exception:
                            pass
                    if fetched:
                        face_imgs = fetched
                        print(f"[agent] #{pid} video faces: scanning {len(fetched)} frames")
                raw = []
                for fim, ftime in face_imgs:
                    W, H = fim.size
                    for f in fi.detect_faces(fim, min_conf):
                        if min_px > 0 and (f.bbox_h * H < min_px or f.bbox_w * W < min_px):
                            continue
                        # Reject non-face-shaped boxes. Interlaced video frames
                        # produce tall/narrow (or very wide) high-confidence false
                        # positives; real faces sit around w/h ~0.9. <0.45 drops
                        # only ~1% of genuine faces (they have other detections).
                        ar = (f.bbox_w / f.bbox_h) if f.bbox_h else 0.0
                        if ar < 0.45 or ar > 1.8:
                            continue
                        raw.append({
                            "bbox_x": f.bbox_x, "bbox_y": f.bbox_y, "bbox_w": f.bbox_w, "bbox_h": f.bbox_h,
                            "confidence": f.confidence, "embedding": f.embedding,
                            "frame_time": ftime,
                        })
                faces = _dedup_faces(raw) if fframes else raw
        except Exception as e:
            print(f"[agent] face detection skipped: {e}")

    payload = {
        "description": desc or None,
        "tags": tags,
        "embedding": None,   # server embeds centrally now
        "faces": faces,
        "faces_done": faces_done,
        "provider": f"remote:{prov.label}",
        "error": None if (desc or faces_only) else "no description",
        "worker": NAME,
        "duration": round(time.time() - t0, 1),
    }
    await client.post(f"{SERVER}/api/remote/result/{pid}", json=payload, headers=HEAD, timeout=180)
    return desc or ""


async def _embed(client: httpx.AsyncClient, job: dict) -> str:
    """Embed mode: jina-clip-v2 IMAGE vector (+ description TEXT vector) → post."""
    t0 = time.time()
    pid = job["photo_id"]
    from app.services import jina_embed
    iv = tv = None
    if job.get("need_image", True):
        r = await client.get(SERVER + job["image_url"], headers=HEAD, timeout=60)
        r.raise_for_status()
        iv = jina_embed.embed_image(Image.open(io.BytesIO(r.content)).convert("RGB"))
    desc = job.get("description")
    if desc and job.get("need_text", True):
        tv = jina_embed.embed_text(desc)
    await client.post(f"{SERVER}/api/remote/embed-result/{pid}", json={
        "embedding": iv, "embedding_text": tv,
        "worker": NAME, "duration": round(time.time() - t0, 1),
    }, headers=HEAD, timeout=120)
    return f"img={'✓' if iv else '–'} txt={'✓' if tv else '–'}"


def _nvenc_available() -> bool:
    import shutil, subprocess
    if not shutil.which("ffmpeg"):
        return False
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, timeout=15).stdout.decode("utf-8", "replace")
        return "h264_nvenc" in out
    except Exception:
        return False


async def _do_transcode(client: httpx.AsyncClient, job: dict, use_nvenc: bool):
    """Download the source, transcode to 1080p web-MP4 (NVENC if available, else
    libx264), upload the result. Temp files under /tmp, always cleaned up."""
    import subprocess, tempfile, os as _os
    pid = job["photo_id"]; res = int(job.get("resolution", 1080))
    long = int(res * 16 / 9)
    src = tempfile.NamedTemporaryFile(suffix=".src", delete=False).name
    out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    try:
        async with client.stream("GET", f"{SERVER}/api/remote/transcode-source/{pid}",
                                 headers=HEAD, timeout=300) as r:
            if r.status_code != 200:
                return f"source HTTP {r.status_code}"
            with open(src, "wb") as fh:
                async for chunk in r.aiter_bytes(1 << 20):
                    fh.write(chunk)
        scale = (f"scale=w='min({long},iw)':h='min({long},ih)'"
                 ":force_original_aspect_ratio=decrease:force_divisible_by=2")
        if use_nvenc:
            cmd = ["ffmpeg", "-nostdin", "-y", "-hwaccel", "cuda", "-i", src, "-vf", scale,
                   "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "6M",
                   "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                   "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
        else:
            cmd = ["ffmpeg", "-nostdin", "-y", "-i", src, "-vf", scale,
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "4",
                   "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                   "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
        p = subprocess.run(cmd, capture_output=True, timeout=1800)
        if p.returncode != 0 or not _os.path.exists(out) or _os.path.getsize(out) < 1000:
            # NVENC hiccup (e.g. odd codec) → one software retry before giving up.
            if use_nvenc:
                return await _do_transcode(client, job, use_nvenc=False)
            return f"ffmpeg rc={p.returncode}"
        with open(out, "rb") as fh:
            up = await client.post(f"{SERVER}/api/remote/transcode-result/{pid}",
                                   params={"resolution": res}, headers=HEAD,
                                   files={"file": (f"{pid}.mp4", fh, "video/mp4")}, timeout=300)
        return "ok" if up.status_code == 200 else f"upload HTTP {up.status_code}"
    finally:
        for f in (src, out):
            try: _os.unlink(f)
            except Exception: pass


async def _transcode_loop(client: httpx.AsyncClient):
    """Parallel loop: drain the server's 1080p transcode backlog on this GPU box."""
    use_nvenc = _nvenc_available()
    print(f"[transcode] loop active (nvenc={use_nvenc})")
    while True:
        try:
            r = await client.get(f"{SERVER}/api/remote/transcode-jobs",
                                  params={"limit": 1}, headers=HEAD, timeout=30)
            jobs = r.json().get("jobs", []) if r.status_code == 200 else []
            if not jobs:
                await asyncio.sleep(20); continue
            for job in jobs:
                t = time.time()
                info = await _do_transcode(client, job, use_nvenc)
                print(f"[transcode] #{job['photo_id']} {info} in {time.time()-t:.1f}s")
        except (httpx.TransportError, OSError):
            await asyncio.sleep(20)
        except Exception as e:
            print(f"[transcode] error: {type(e).__name__}: {e}")
            await asyncio.sleep(20)


async def _claim_loop(client: httpx.AsyncClient):
    fails = 0   # consecutive connection failures → back off, keep retrying until the server is back
    while True:
            try:
                r = await client.post(f"{SERVER}/api/remote/claim",
                                      json={"worker": NAME, "mode": MODE, "media": MEDIA},
                                      headers=HEAD, timeout=30)
                if r.status_code != 200:
                    fails += 1
                    wait = min(60, POLL * 3 * fails)
                    print(f"[agent] Server nicht erreichbar (HTTP {r.status_code}, #{fails}) — pausiere {wait}s …")
                    await asyncio.sleep(wait)
                    continue
                if fails:
                    print("[agent] Server wieder erreichbar — mache weiter."); fails = 0
                job = r.json()
                if not job.get("photo_id"):
                    await asyncio.sleep(POLL)
                    continue
                t = time.time()
                if job.get("mode") == "embed":
                    info = await _embed(client, job)
                    print(f"[agent] #{job['photo_id']} embed in {time.time() - t:.1f}s: {info}")
                else:
                    desc = await _process(client, job)
                    print(f"[agent] #{job['photo_id']} done in {time.time() - t:.1f}s: {desc[:60]}")
            except (httpx.TransportError, OSError) as e:
                # Server/Netz weg (Server aus, Deploy-Neustart, Netz-Blip): PAUSE +
                # Backoff (bis 60s), endlos weiter prüfen bis er zurück ist.
                fails += 1
                wait = min(60, POLL * 3 * fails)
                print(f"[agent] Server/Netz nicht erreichbar (#{fails}) — pausiere {wait}s … ({type(e).__name__})")
                await asyncio.sleep(wait)
            except Exception as e:
                # einzelner Job kaputt → überspringen, kurz weiter
                print(f"[agent] Job übersprungen: {type(e).__name__}: {e}")
                await asyncio.sleep(POLL)


async def main():
    if not TOKEN:
        print("[agent] PHOTOFLOW_REMOTE_TOKEN not set — aborting.")
        return
    print(f"[agent] '{NAME}' → {SERVER} (poll {POLL}s, mode={MODE}, media={MEDIA}, backend={BACKEND})")
    # Transcode help: ON by default where ffmpeg+NVENC exist (the Asus GPU box) and
    # the AI jobs are winding down. REMOTE_TRANSCODE=0 disables; =1 forces (software).
    flag = (os.getenv("REMOTE_TRANSCODE") or "").strip().lower()
    do_transcode = flag in ("1", "true", "yes") or (flag not in ("0", "false", "no") and _nvenc_available())
    async with httpx.AsyncClient() as client:
        loops = [_claim_loop(client)]
        if do_transcode:
            loops.append(_transcode_loop(client))
        await asyncio.gather(*loops)


if __name__ == "__main__":
    asyncio.run(main())
