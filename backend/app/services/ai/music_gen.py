"""AI music generation for highlight soundtracks — license-clean models only.

Two cloud models (fal, different quality tiers) + two local quality tiers
(stable-audio-open via diffusers). All Stability / royalty-free trained → safe
to use under videos users may share publicly. NEVER add Suno/MusicGen-NC here.

Privacy: only a short MOOD TEXT prompt leaves the machine for cloud generation —
never the user's photos.

Everything degrades gracefully: a failure raises MusicGenError and the caller
falls back to the library / a manual file / no music, so a render never breaks.
"""
import asyncio
import base64
from typing import Optional

import httpx

_FAL_BASE = "https://queue.fal.run"

# Cloud model ids (fal). Max 47s per clip → caller loops it under the slideshow.
FAL_MODELS = {
    "fal_open": "fal-ai/stable-audio",                    # cheaper, Stable Audio Open
    "fal_25":   "fal-ai/stable-audio-25/text-to-audio",  # premium, Stable Audio 2.5
}
MAX_SECONDS = 47


class MusicGenError(RuntimeError):
    pass


def _extract_audio_url(data: dict) -> Optional[str]:
    """fal audio models return {'audio_file':{'url'}} | {'audio':{'url'}} | {'audio_url'}."""
    if not isinstance(data, dict):
        return None
    for node in (data, data.get("output") or {}):
        if not isinstance(node, dict):
            continue
        for key in ("audio_file", "audio"):
            v = node.get(key)
            if isinstance(v, dict) and v.get("url"):
                return v["url"]
            if isinstance(v, str) and v.startswith("http"):
                return v
        if isinstance(node.get("audio_url"), str):
            return node["audio_url"]
    return None


async def fal_generate(api_key: str, prompt: str, seconds: float,
                       model_key: str = "fal_open",
                       poll_interval: float = 4.0, poll_timeout: float = 240.0) -> bytes:
    """Generate an instrumental track via fal Stable Audio. Returns audio bytes."""
    if not api_key:
        raise MusicGenError("Kein fal.ai API-Key konfiguriert (highlights.fal_api_key).")
    model = FAL_MODELS.get(model_key, FAL_MODELS["fal_open"])
    secs = max(5, min(MAX_SECONDS, int(seconds)))
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "seconds_total": secs}

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(f"{_FAL_BASE}/{model}", headers=headers, json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MusicGenError(f"fal-Start fehlgeschlagen ({e.response.status_code}): "
                                f"{e.response.text[:300]}") from e
        sub = r.json()
        req_id = sub.get("request_id")
        if not req_id:
            raise MusicGenError("fal-Antwort ohne request_id.")
        status_url = sub.get("status_url") or f"{_FAL_BASE}/{model}/requests/{req_id}/status"
        result_url = sub.get("response_url") or f"{_FAL_BASE}/{model}/requests/{req_id}"

        waited = 0.0
        while waited < poll_timeout:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            st = await client.get(status_url, headers=headers)
            st.raise_for_status()
            status = (st.json() or {}).get("status", "")
            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR", "CANCELLED"):
                raise MusicGenError(f"fal-Job {status}: {st.text[:300]}")
        else:
            raise MusicGenError(f"fal-Musik Timeout nach {int(poll_timeout)}s.")

        res = await client.get(result_url, headers=headers)
        res.raise_for_status()
        url = _extract_audio_url(res.json())
        if not url:
            raise MusicGenError("fal fertig, aber keine Audio-URL in der Antwort.")
        ar = await client.get(url, follow_redirects=True, timeout=180)
        ar.raise_for_status()
        return ar.content


def local_generate(prompt: str, seconds: float, quality: str = "fast") -> bytes:
    """Generate a track locally with stable-audio-open via diffusers' StableAudioPipeline.
    Lazy + optional: raises MusicGenError if diffusers/model aren't installed, so the
    caller falls back. 'fast' vs 'quality' = fewer/more denoise steps.

    Needs (on the worker, like the M3-LTX video path): `pip install diffusers soundfile`
    + the stabilityai/stable-audio-open-1.0 weights.
    """
    try:
        import io
        import torch                       # noqa
        import soundfile as sf
        from diffusers import StableAudioPipeline
    except Exception as e:
        raise MusicGenError(f"Lokales Musik-Modell nicht installiert ({e}).") from e
    try:
        secs = max(5, min(MAX_SECONDS, int(seconds)))
        steps = 60 if quality == "fast" else 140
        device = "cuda" if torch.cuda.is_available() else ("mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu")
        dtype = torch.float16 if device == "cuda" else torch.float32
        pipe = StableAudioPipeline.from_pretrained("stabilityai/stable-audio-open-1.0", torch_dtype=dtype).to(device)
        audio = pipe(prompt=prompt, negative_prompt="low quality, distorted",
                     num_inference_steps=steps, audio_end_in_s=float(secs)).audios[0]
        buf = io.BytesIO()
        sf.write(buf, audio.T.float().cpu().numpy(), pipe.vae.sampling_rate, format="WAV")
        return buf.getvalue()
    except MusicGenError:
        raise
    except Exception as e:
        raise MusicGenError(f"Lokale Musik-Generierung fehlgeschlagen: {str(e)[:200]}") from e
