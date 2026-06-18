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
                {"model": MODEL, "prompt": prompt, "images": [b64], "stream": False,
                 # think=false: thinking models (e.g. gemma4) otherwise emit a long
                 # reasoning chain (1000+ tokens) before the answer → very slow.
                 "think": False,
                 "keep_alive": "30m",  # keep the model resident between photos (no 50s reload)
                 "options": {
                     # num_ctx=4096 instead of the model's 256K default: describing ONE
                     # image needs ~2k tokens, and a 256K context allocates a huge KV
                     # cache → slow + memory-heavy. num_predict caps a runaway output.
                     "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "4096")),
                     "num_predict": int(os.environ.get("OLLAMA_NUM_PREDICT", "512")),
                 }},
                timeout=timeout)
    return (out.get("response") or "").strip()


def _split_desc_tags(raw):
    """Split a combined '<description> … TAGS: a, b, c' response."""
    low = raw.lower()
    i = low.rfind("tags:")
    if i < 0:
        return raw.strip(), []
    desc = raw[:i].strip().rstrip("\n").rstrip()
    tagpart = raw[i + 5:]
    tags, seen = [], set()
    for t in tagpart.replace("\n", ",").split(","):
        t = t.strip().lstrip("-•*").strip().lower()
        if t and t not in seen:
            seen.add(t); tags.append(t)
    return desc, tags[:20]


def main():
    import urllib.error
    if not TOKEN:
        print("PHOTOFLOW_REMOTE_TOKEN fehlt — abbruch."); sys.exit(1)
    print(f"[mac] {NAME} → {SERVER}  mode={MODE} media={MEDIA} model={MODEL}")
    fails = 0   # consecutive connection failures → back off, keep retrying
    while True:
        try:
            job = _post(f"{SERVER}/api/remote/claim",
                        {"worker": NAME, "mode": MODE, "media": MEDIA}, timeout=30)
            if fails:
                print(f"[mac] Server wieder erreichbar — mache weiter."); fails = 0
            pid = job.get("photo_id")
            if not pid:
                time.sleep(POLL); continue
            t = time.time()
            b64 = base64.b64encode(_get(SERVER + job["image_url"])).decode()
            lang = job.get("language", "de")
            dprompt = job.get("prompt") or f"Beschreibe dieses Foto sachlich auf {lang}."
            tprompt = job.get("tag_prompt") or "10-15 kurze Schlagwörter, kommagetrennt, nur Stichwörter"
            # ONE call: description + tags together (image processed once, not twice).
            raw = _ollama(f"{dprompt}\n\nGib anschließend in einer NEUEN Zeile, beginnend mit "
                          f"'TAGS:', {tprompt}.", b64)
            desc, tags = _split_desc_tags(raw)
            _post(f"{SERVER}/api/remote/result/{pid}", {
                "description": desc or None, "tags": tags, "embedding": None,
                "faces": [], "faces_done": False,
                "provider": f"remote:ollama:{MODEL}", "worker": NAME,
                "duration": round(time.time() - t, 1),
                "error": None if desc else "no description",
            }, timeout=120)
            print(f"[mac] #{pid} {round(time.time()-t,1)}s: {desc[:70]}")
        except (urllib.error.URLError, OSError, ConnectionError, TimeoutError) as e:
            # Server/Netz nicht erreichbar (Server aus, Deploy-Neustart, WLAN weg):
            # PAUSE + Backoff (bis 60s), endlos weiter prüfen, bis er wieder da ist.
            fails += 1
            wait = min(60, POLL * 3 * fails)
            print(f"[mac] Server nicht erreichbar (#{fails}) — pausiere {wait}s, prüfe weiter … ({type(e).__name__})")
            time.sleep(wait)
        except Exception as e:
            # einzelnes Bild kaputt o. Ä. → überspringen, kurz weiter
            print(f"[mac] Bild übersprungen: {type(e).__name__}: {e}")
            time.sleep(POLL)


if __name__ == "__main__":
    main()
