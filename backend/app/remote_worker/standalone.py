#!/usr/bin/env python3
"""NimtaFlow standalone worker — Ollama describe mode.

Self-contained: no NimtaFlow repo needed. Only requires httpx + Pillow.

Install & run:
  pip install httpx pillow
  PHOTOFLOW_SERVER=http://192.168.0.193:8090 \\
  PHOTOFLOW_REMOTE_TOKEN=yourtoken \\
  OLLAMA_MODEL=gemma4:27b \\
  python worker.py

Or let the curl installer do this automatically:
  curl -sSL "http://your-server:8090/api/remote/install?token=..." | bash

Env vars:
  PHOTOFLOW_SERVER       e.g. http://192.168.0.193:8090
  PHOTOFLOW_REMOTE_TOKEN token from Settings → Remote Worker
  WORKER_NAME            optional, defaults to hostname
  WORKER_MEDIA           images | videos | both (default: images)
  OLLAMA_URL             default http://localhost:11434
  OLLAMA_MODEL           default gemma4:27b
  POLL_INTERVAL          seconds between polls (default 5)
"""
import asyncio
import base64
import io
import os
import socket
import time

import httpx
from PIL import Image

SERVER = os.getenv("PHOTOFLOW_SERVER", "http://localhost:8090").rstrip("/")
TOKEN = os.getenv("PHOTOFLOW_REMOTE_TOKEN", "")
NAME = os.getenv("WORKER_NAME") or socket.gethostname()
MEDIA = (os.getenv("WORKER_MEDIA") or "images").strip().lower()
OLLAMA_URL = (os.getenv("OLLAMA_URL") or "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or "gemma4:27b"
POLL = float(os.getenv("POLL_INTERVAL", "5"))
HEAD = {"X-Remote-Token": TOKEN}


def _img_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


async def _describe(img: Image.Image, language: str, prompt=None, frames=None) -> str:
    lang_map = {"de": "German", "en": "English", "fr": "French"}
    lang = lang_map.get(language, "German")
    the_prompt = prompt or (
        f"Describe this photo in {lang} in 2-3 sentences. "
        "Describe people, places, activities and mood."
    )
    if frames:
        imgs = []
        for fr in frames[:8]:
            fr = fr.convert("RGB")
            if max(fr.size) > 768:
                fr.thumbnail((768, 768), Image.LANCZOS)
            imgs.append(_img_b64(fr))
    else:
        imgs = [_img_b64(img)]
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": the_prompt, "images": imgs, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()


async def _generate_tags(img: Image.Image, language: str, prompt=None) -> list:
    lang = {"de": "auf Deutsch", "en": "in English", "fr": "en français"}.get(language, "auf Deutsch")
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt or (
                    f"Liste bis zu 15 beschreibende Schlagwörter {lang} für dieses Foto. "
                    "Nur eine kommagetrennte Liste."
                ),
                "images": [_img_b64(img)],
                "stream": False,
            },
        )
        resp.raise_for_status()
        text = resp.json()["response"].strip()
        return [t.strip().lower() for t in text.split(",") if t.strip()]


async def _process(client: httpx.AsyncClient, job: dict) -> str:
    t0 = time.time()
    pid = job["photo_id"]

    r = await client.get(SERVER + job["image_url"], headers=HEAD, timeout=60)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")

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
        if not frames:
            frames = None
        else:
            print(f"[agent] #{pid} video: {len(frames)} frames")

    faces_only = bool(job.get("faces_only"))
    if faces_only:
        desc, tags = None, []
    else:
        lang = job.get("language", "de")
        desc = await _describe(img, lang, job.get("prompt"), frames)
        tags = await _generate_tags(img, lang, job.get("tag_prompt")) if desc else []

    payload = {
        "description": desc or None,
        "tags": tags,
        "embedding": None,
        "faces": [],
        "faces_done": False,
        "provider": f"remote:ollama:{OLLAMA_MODEL}",
        "error": None if (desc or faces_only) else "no description",
        "worker": NAME,
        "duration": round(time.time() - t0, 1),
    }
    await client.post(
        f"{SERVER}/api/remote/result/{pid}", json=payload, headers=HEAD, timeout=180
    )
    return desc or ""


async def _claim_loop(client: httpx.AsyncClient):
    fails = 0
    while True:
        try:
            r = await client.post(
                f"{SERVER}/api/remote/claim",
                json={"worker": NAME, "mode": "describe", "media": MEDIA},
                headers=HEAD,
                timeout=30,
            )
            if r.status_code != 200:
                fails += 1
                wait = min(60, POLL * 3 * fails)
                print(
                    f"[agent] Server nicht erreichbar (HTTP {r.status_code}, #{fails})"
                    f" — pausiere {wait:.0f}s …"
                )
                await asyncio.sleep(wait)
                continue
            if fails:
                print("[agent] Server wieder erreichbar — mache weiter.")
                fails = 0
            job = r.json()
            if not job.get("photo_id"):
                await asyncio.sleep(POLL)
                continue
            t = time.time()
            desc = await _process(client, job)
            print(
                f"[agent] #{job['photo_id']} done in {time.time() - t:.1f}s:"
                f" {desc[:60]}"
            )
        except (httpx.TransportError, OSError) as e:
            fails += 1
            wait = min(60, POLL * 3 * fails)
            print(
                f"[agent] Netz nicht erreichbar (#{fails}) — pausiere {wait:.0f}s"
                f" … ({type(e).__name__})"
            )
            await asyncio.sleep(wait)
        except Exception as e:
            print(f"[agent] Job übersprungen: {type(e).__name__}: {e}")
            await asyncio.sleep(POLL)


async def main():
    if not TOKEN:
        print("[agent] PHOTOFLOW_REMOTE_TOKEN nicht gesetzt — abbruch.")
        return
    print(
        f"[agent] '{NAME}' → {SERVER}"
        f" (poll {POLL}s, media={MEDIA}, model={OLLAMA_MODEL})"
    )
    async with httpx.AsyncClient() as client:
        await _claim_loop(client)


if __name__ == "__main__":
    asyncio.run(main())
