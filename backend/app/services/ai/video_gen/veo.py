"""Google Veo 3.1 image-to-video via the Gemini REST API (no SDK — httpx, like
ai/gemini.py). Long-running: POST :predictLongRunning → poll the operation →
download the resulting MP4. Returns the video bytes.

Docs: https://ai.google.dev/gemini-api/docs/video
Pricing (Jun 2026): veo-3.1-fast ≈ $0.15/s incl. audio. Caller MUST enforce a budget.
"""
import asyncio
import base64
from typing import Optional

import httpx

_BASE = "https://generativelanguage.googleapis.com/v1beta"
_VALID_SECONDS = {"4", "6", "8"}


class VeoError(RuntimeError):
    pass


async def animate_image(
    api_key: str,
    image_bytes: bytes,
    prompt: str,
    *,
    mime: str = "image/jpeg",
    seconds: int = 4,
    resolution: str = "720p",
    aspect: str = "16:9",
    model: str = "veo-3.1-fast-generate-preview",
    poll_interval: float = 10.0,
    poll_timeout: float = 600.0,
) -> bytes:
    """Animate a single still image into a short MP4. Blocks (async) until the clip
    is ready or `poll_timeout` is hit. Raises VeoError on any failure."""
    if not api_key:
        raise VeoError("Kein Gemini/Veo API-Key konfiguriert (ai.gemini.api_key).")
    dur = str(seconds) if str(seconds) in _VALID_SECONDS else "4"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "instances": [{
            "prompt": prompt,
            "image": {"inlineData": {"mimeType": mime,
                                     "data": base64.b64encode(image_bytes).decode()}},
        }],
        "parameters": {"aspectRatio": aspect, "durationSeconds": dur, "resolution": resolution},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(f"{_BASE}/models/{model}:predictLongRunning",
                                  headers=headers, json=body)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise VeoError(f"Veo-Start fehlgeschlagen ({e.response.status_code}): "
                           f"{e.response.text[:300]}") from e
        op = r.json().get("name")
        if not op:
            raise VeoError("Veo-Antwort ohne Operation-Name.")

        waited = 0.0
        while waited < poll_timeout:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            pr = await client.get(f"{_BASE}/{op}", headers=headers)
            pr.raise_for_status()
            data = pr.json()
            if data.get("error"):
                raise VeoError(f"Veo-Fehler: {str(data['error'])[:300]}")
            if not data.get("done"):
                continue
            uri = _extract_uri(data)
            if not uri:
                raise VeoError("Veo fertig, aber keine Video-URI in der Antwort.")
            vr = await client.get(uri, headers={"x-goog-api-key": api_key},
                                  follow_redirects=True, timeout=180)
            vr.raise_for_status()
            return vr.content
        raise VeoError(f"Veo-Generierung Timeout nach {int(poll_timeout)}s.")


def _extract_uri(data: dict) -> Optional[str]:
    try:
        samples = data["response"]["generateVideoResponse"]["generatedSamples"]
        return samples[0]["video"]["uri"]
    except (KeyError, IndexError, TypeError):
        return None
