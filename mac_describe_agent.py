#!/usr/bin/env python3
"""Standalone PhotoFlow describe-worker for a Mac running Ollama.

No pip, no Docker, no nvidia — pure Python stdlib. It polls a remote PhotoFlow
server for describe jobs, runs the image through the LOCAL Ollama (e.g. gemma4),
and posts description + tags back. Faces + embeddings are handled elsewhere
(Asus); this worker ONLY describes (faces_done=False stays for the faces worker).

Run on the Mac (Ollama must be running + the model pulled):

    PHOTOFLOW_SERVER=http://your-server:8090 \
    PHOTOFLOW_REMOTE_TOKEN=<token> \
    WORKER_NAME=m3-describe WORKER_MODE=describe WORKER_MEDIA=images \
    OLLAMA_MODEL=gemma4:26b \
    python3 mac_describe_agent.py
"""
import os, sys, json, time, base64, urllib.request

SERVER = os.environ.get("PHOTOFLOW_SERVER", "http://your-server:8090").rstrip("/")
TOKEN  = os.environ.get("PHOTOFLOW_REMOTE_TOKEN", "")
NAME   = os.environ.get("WORKER_NAME", "m3-describe")
MODE   = os.environ.get("WORKER_MODE", "describe")
MEDIA  = os.environ.get("WORKER_MEDIA", "images")
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL  = os.environ.get("OLLAMA_MODEL", "gemma4:26b")
POLL   = float(os.environ.get("POLL_INTERVAL", "5"))
H      = {"X-Remote-Token": TOKEN}


def _post(url, data, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", **H}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _ollama(prompt, b64, timeout=300):
    out = _post(f"{OLLAMA}/api/generate",
                {"model": MODEL, "prompt": prompt, "images": [b64], "stream": False},
                timeout=timeout)
    return (out.get("response") or "").strip()


def main():
    if not TOKEN:
        print("PHOTOFLOW_REMOTE_TOKEN fehlt — abbruch."); sys.exit(1)
    print(f"[mac] {NAME} → {SERVER}  mode={MODE} media={MEDIA} model={MODEL}")
    while True:
        try:
            job = _post(f"{SERVER}/api/remote/claim",
                        {"worker": NAME, "mode": MODE, "media": MEDIA}, timeout=30)
            pid = job.get("photo_id")
            if not pid:
                time.sleep(POLL); continue
            t = time.time()
            b64 = base64.b64encode(_get(SERVER + job["image_url"])).decode()
            lang = job.get("language", "de")
            desc = _ollama(job.get("prompt") or f"Beschreibe dieses Foto sachlich auf {lang}.", b64)
            tprompt = job.get("tag_prompt") or \
                "Nenne 10-15 kurze Schlagwörter zu diesem Bild, kommagetrennt, nur Stichwörter."
            tags_raw = _ollama(tprompt, b64) if desc else ""
            tags = [x.strip().lower() for x in tags_raw.replace("\n", ",").split(",") if x.strip()][:20]
            _post(f"{SERVER}/api/remote/result/{pid}", {
                "description": desc or None, "tags": tags, "embedding": None,
                "faces": [], "faces_done": False,
                "provider": f"remote:ollama:{MODEL}", "worker": NAME,
                "duration": round(time.time() - t, 1),
                "error": None if desc else "no description",
            }, timeout=120)
            print(f"[mac] #{pid} {round(time.time()-t,1)}s: {desc[:70]}")
        except Exception as e:
            print(f"[mac] error: {type(e).__name__}: {e}")
            time.sleep(POLL * 3)


if __name__ == "__main__":
    main()
