#!/usr/bin/env python3
"""Native-video describe-worker for a Mac with MLX (Qwen3-VL via mlx-vlm).

Runs the LOCAL Qwen3-VL model (loaded ONCE, kept resident) over PhotoFlow video
jobs: claim → download the server's pre-transcoded 1080p web MP4 → describe the
whole clip NATIVELY (temporal: scenes/motion over the duration, not a single
frame) → post description + tags back. Frame count + answer length scale with the
video's duration (no fixed sentence cap). Faces/embeddings are handled elsewhere.

Run under the mlx-vlm venv (NOT system python):

    PHOTOFLOW_SERVER=http://your-server:8090 \
    PHOTOFLOW_REMOTE_TOKEN=<token> \
    WORKER_NAME=m3-video WORKER_MODE=describe WORKER_MEDIA=videos \
    MLX_MODEL=mlx-community/Qwen3-VL-8B-Instruct-8bit \
    ~/photoflow_worker/mlxtest/venv/bin/python mac_video_agent.py
"""
import os, sys, json, time, tempfile, urllib.request, urllib.error

SERVER = os.environ.get("PHOTOFLOW_SERVER", "http://your-server:8090").rstrip("/")
TOKEN  = os.environ.get("PHOTOFLOW_REMOTE_TOKEN", "")
NAME   = os.environ.get("WORKER_NAME", "m3-video")
MODE   = os.environ.get("WORKER_MODE", "describe")
MEDIA  = os.environ.get("WORKER_MEDIA", "videos")
MODEL  = os.environ.get("MLX_MODEL", "mlx-community/Qwen3-VL-8B-Instruct-8bit")
POLL   = float(os.environ.get("POLL_INTERVAL", "5"))
H      = {"X-Remote-Token": TOKEN}

DEFAULT_PROMPT = (
    "Beschreibe den zeitlichen ABLAUF dieses Videos auf Deutsch. Gliedere nach dem "
    "Verlauf: Was passiert zuerst, was veraendert sich, was passiert am Ende? "
    "Beschreibe die einzelnen Abschnitte/Szenen nacheinander - wer und was zu sehen "
    "ist, Bewegungen, Orts- und Szenenwechsel. So ausfuehrlich wie noetig, lass "
    "nichts Wesentliches aus."
)
DEFAULT_TAGS = "10-20 kurze deutsche Schlagwoerter, kommagetrennt, nur Stichwoerter"


def _post(url, data, timeout=180):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", **H}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _download(url, dest, timeout=300):
    req = urllib.request.Request(url, headers=H)
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def _split_desc_tags(raw):
    """Split a combined '<description> … TAGS: a, b, c' response."""
    low = raw.lower()
    i = low.rfind("tags:")
    if i < 0:
        return raw.strip(), []
    desc = raw[:i].strip().rstrip("\n").rstrip()
    tags, seen = [], set()
    for t in raw[i + 5:].replace("\n", ",").split(","):
        t = t.strip().lstrip("-•*").strip().lower()
        if t and t not in seen:
            seen.add(t); tags.append(t)
    return desc, tags[:25]


def _plan(duration):
    """Duration-adaptive sampling + answer length. Cap frames at 32 so a long clip
    never explodes the context; scale max_tokens with length but never tiny."""
    d = max(1.0, float(duration or 1))
    target_frames = min(32, max(8, int(d)))
    fps = round(min(2.0, target_frames / d), 3)
    max_tokens = min(1200, 360 + int(d * 6))
    return fps, max_tokens


def main():
    print(f"[m3-video] lade Modell {MODEL} … (einmalig)", flush=True)
    from mlx_vlm import load, generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import load_config
    t0 = time.time()
    model, processor = load(MODEL)
    config = load_config(MODEL)
    print(f"[m3-video] Modell geladen in {time.time()-t0:.1f}s → {NAME} → {SERVER}  "
          f"mode={MODE} media={MEDIA}", flush=True)
    if not TOKEN:
        print("PHOTOFLOW_REMOTE_TOKEN fehlt — abbruch."); sys.exit(1)

    fails = 0
    while True:
        tmp = None
        try:
            job = _post(f"{SERVER}/api/remote/claim",
                        {"worker": NAME, "mode": MODE, "media": MEDIA}, timeout=30)
            if fails:
                print("[m3-video] Server wieder erreichbar — mache weiter."); fails = 0
            pid = job.get("photo_id")
            vurl = job.get("video_url")
            if not pid or not vurl:
                time.sleep(POLL); continue
            t = time.time()
            fps, max_tokens = _plan(job.get("duration"))
            # download the 1080p web mp4 to a temp file
            fd, tmp = tempfile.mkstemp(suffix=".mp4"); os.close(fd)
            _download(SERVER + vurl, tmp)
            lang = job.get("language", "de")
            dprompt = job.get("prompt") or DEFAULT_PROMPT
            tprompt = job.get("tag_prompt") or DEFAULT_TAGS
            full = (f"{dprompt}\n\nGib anschliessend in einer NEUEN Zeile, beginnend mit "
                    f"'TAGS:', {tprompt}.")
            fmt = apply_chat_template(processor, config, full, num_images=0, num_audios=0,
                                      video=tmp, fps=fps)
            r = generate(model, processor, fmt, video=tmp, fps=fps,
                         max_tokens=max_tokens, verbose=False)
            desc, tags = _split_desc_tags(r.text or "")
            _post(f"{SERVER}/api/remote/result/{pid}", {
                "description": desc or None, "tags": tags, "embedding": None,
                "faces": [], "faces_done": False,
                "provider": f"remote:mlx:{MODEL.split('/')[-1]}", "worker": NAME,
                "duration": round(time.time() - t, 1),
                "error": None if desc else "no description",
            }, timeout=120)
            print(f"[m3-video] #{pid} {round(time.time()-t,1)}s (fps={fps}, "
                  f"{r.generation_tokens}tok): {desc[:70]}", flush=True)
        except urllib.error.HTTPError as e:
            try:
                body = e.read(300).decode("utf-8", "replace").replace("\n", " ").strip()
            except Exception:
                body = ""
            if e.code in (404, 410, 422):
                # video not transcoded yet / gone — skip, try the next claim.
                print(f"[m3-video] Video übersprungen (HTTP {e.code}: {body[:80]})")
                time.sleep(POLL)
            else:
                fails += 1; wait = min(60, POLL * 3 * fails)
                print(f"[m3-video] Server-Antwort HTTP {e.code} bei {e.url} (#{fails}) — "
                      f"warte {wait}s … {body[:120]}")
                time.sleep(wait)
        except (urllib.error.URLError, OSError, ConnectionError, TimeoutError) as e:
            fails += 1; wait = min(60, POLL * 3 * fails)
            print(f"[m3-video] Server nicht erreichbar (#{fails}) — pausiere {wait}s … "
                  f"({type(e).__name__})")
            time.sleep(wait)
        except Exception as e:
            print(f"[m3-video] Video übersprungen: {type(e).__name__}: {e}")
            time.sleep(POLL)
        finally:
            if tmp and os.path.exists(tmp):
                try: os.remove(tmp)
                except Exception: pass


if __name__ == "__main__":
    main()
