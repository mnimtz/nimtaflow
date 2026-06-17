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
MODE = (os.getenv("WORKER_MODE") or "all").strip().lower()  # "all" | "faces"
HEAD = {"X-Remote-Token": TOKEN}


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

    from app.services.ai.local_vlm import LocalVLMProvider
    prov = LocalVLMProvider(job.get("model", "florence2-base"))
    lang = job.get("language", "de")
    prompt = job.get("prompt")

    # faces_only: the photo already has an (imported) description — only run face
    # detection, don't re-describe/re-tag/re-embed.
    faces_only = bool(job.get("faces_only"))
    if faces_only:
        desc, tags, emb = None, [], []
    else:
        desc = await prov.describe_image(img, lang, prompt, frames=frames)
        # Reuse the description we just generated for tag extraction instead of a
        # second full VLM pass (~halves per-photo time when no JSON tag prompt).
        tags = await prov.generate_tags(img, lang, job.get("tag_prompt"), caption=desc) if desc else []
        emb = await prov.embed_text(desc) if desc else []

    faces = []
    if job.get("faces_enabled", True):
        try:
            from app.services import face_detect_insightface as fi
            if fi.available():
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
        "embedding": emb or None,
        "faces": faces,
        "provider": f"remote:{prov.label}",
        "error": None if (desc or faces_only) else "no description",
        "worker": NAME,
        "duration": round(time.time() - t0, 1),
    }
    await client.post(f"{SERVER}/api/remote/result/{pid}", json=payload, headers=HEAD, timeout=180)
    return desc or ""


async def main():
    if not TOKEN:
        print("[agent] PHOTOFLOW_REMOTE_TOKEN not set — aborting.")
        return
    print(f"[agent] '{NAME}' → {SERVER} (poll {POLL}s, mode={MODE})")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.post(f"{SERVER}/api/remote/claim", json={"worker": NAME, "mode": MODE}, headers=HEAD, timeout=30)
                if r.status_code != 200:
                    print(f"[agent] claim HTTP {r.status_code}: {r.text[:140]}")
                    await asyncio.sleep(POLL * 3)
                    continue
                job = r.json()
                if not job.get("photo_id"):
                    await asyncio.sleep(POLL)
                    continue
                t = time.time()
                desc = await _process(client, job)
                print(f"[agent] #{job['photo_id']} done in {time.time() - t:.1f}s: {desc[:60]}")
            except Exception as e:
                print(f"[agent] error: {type(e).__name__}: {e}")
                await asyncio.sleep(POLL * 3)


if __name__ == "__main__":
    asyncio.run(main())
