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
HEAD = {"X-Remote-Token": TOKEN}


async def _process(client: httpx.AsyncClient, job: dict) -> str:
    t0 = time.time()
    pid = job["photo_id"]
    r = await client.get(SERVER + job["image_url"], headers=HEAD, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")

    from app.services.ai.local_vlm import LocalVLMProvider
    prov = LocalVLMProvider(job.get("model", "florence2-base"))
    lang = job.get("language", "de")
    prompt = job.get("prompt")

    desc = await prov.describe_image(img, lang, prompt)
    tags = await prov.generate_tags(img, lang, job.get("tag_prompt")) if desc else []
    emb = await prov.embed_text(desc) if desc else []

    faces = []
    if job.get("faces_enabled", True):
        try:
            from app.services import face_detect_insightface as fi
            if fi.available():
                min_px = float(job.get("min_face_px", 0) or 0)
                min_conf = float(job.get("min_conf", 0.5) or 0.5)
                W, H = img.size
                for f in fi.detect_faces(img, min_conf):
                    if min_px > 0 and (f.bbox_h * H < min_px or f.bbox_w * W < min_px):
                        continue  # skip tiny/background faces (junk-cluster source)
                    faces.append({
                        "bbox_x": f.bbox_x, "bbox_y": f.bbox_y, "bbox_w": f.bbox_w, "bbox_h": f.bbox_h,
                        "confidence": f.confidence, "embedding": f.embedding,
                    })
        except Exception as e:
            print(f"[agent] face detection skipped: {e}")

    payload = {
        "description": desc or None,
        "tags": tags,
        "embedding": emb or None,
        "faces": faces,
        "provider": f"remote:{prov.label}",
        "error": None if desc else "no description",
        "worker": NAME,
        "duration": round(time.time() - t0, 1),
    }
    await client.post(f"{SERVER}/api/remote/result/{pid}", json=payload, headers=HEAD, timeout=180)
    return desc or ""


async def main():
    if not TOKEN:
        print("[agent] PHOTOFLOW_REMOTE_TOKEN not set — aborting.")
        return
    print(f"[agent] '{NAME}' → {SERVER} (poll {POLL}s)")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.post(f"{SERVER}/api/remote/claim", json={"worker": NAME}, headers=HEAD, timeout=30)
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
