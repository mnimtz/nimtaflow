"""fal.ai image-to-video via its Queue REST API (httpx, no SDK).

One key, many models (Hailuo cheap … Veo/Sora premium). fal gives ~$20 free credits,
so this is the path to actually TEST image-to-video for free. Model id is configurable
(highlights.fal_model). Image is passed inline as a base64 data URI in `image_url`.

Docs: https://fal.ai/docs/model-endpoints/queue
"""
import asyncio
import base64
from typing import Optional

import httpx

_BASE = "https://queue.fal.run"
DEFAULT_MODEL = "fal-ai/minimax/hailuo-02/standard/image-to-video"


class FalError(RuntimeError):
    pass


async def animate_image(
    api_key: str,
    image_bytes: bytes,
    prompt: str,
    *,
    mime: str = "image/jpeg",
    model: str = DEFAULT_MODEL,
    poll_interval: float = 5.0,
    poll_timeout: float = 600.0,
) -> bytes:
    """Animate a still image into a short MP4 via a fal.ai i2v model. Blocks (async)
    until done or timeout. Returns the video bytes. Raises FalError on failure."""
    if not api_key:
        raise FalError("Kein fal.ai API-Key konfiguriert (highlights.fal_api_key).")
    model = (model or DEFAULT_MODEL).strip("/")
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    payload = {"prompt": prompt, "image_url": data_uri}

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(f"{_BASE}/{model}", headers=headers, json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise FalError(f"fal-Start fehlgeschlagen ({e.response.status_code}): "
                           f"{e.response.text[:300]}") from e
        sub = r.json()
        req_id = sub.get("request_id")
        status_url = sub.get("status_url") or f"{_BASE}/{model}/requests/{req_id}/status"
        result_url = sub.get("response_url") or f"{_BASE}/{model}/requests/{req_id}"
        if not req_id:
            raise FalError("fal-Antwort ohne request_id.")

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
                raise FalError(f"fal-Job {status}: {st.text[:300]}")
        else:
            raise FalError(f"fal-Generierung Timeout nach {int(poll_timeout)}s.")

        res = await client.get(result_url, headers=headers)
        res.raise_for_status()
        url = _extract_video_url(res.json())
        if not url:
            raise FalError("fal fertig, aber keine Video-URL in der Antwort.")
        vr = await client.get(url, follow_redirects=True, timeout=180)
        vr.raise_for_status()
        return vr.content


def _extract_video_url(data: dict) -> Optional[str]:
    """fal video models vary: {'video': {'url'}} | {'videos':[{'url'}]} | {'output':{...}}."""
    if not isinstance(data, dict):
        return None
    for node in (data, data.get("output") or {}):
        if not isinstance(node, dict):
            continue
        v = node.get("video")
        if isinstance(v, dict) and v.get("url"):
            return v["url"]
        if isinstance(v, str) and v.startswith("http"):
            return v
        vs = node.get("videos")
        if isinstance(vs, list) and vs and isinstance(vs[0], dict) and vs[0].get("url"):
            return vs[0]["url"]
    return None
