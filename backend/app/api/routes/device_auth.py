"""Device Authorization Flow (RFC 8628 inspired).

TV/FireTV apps can't type passwords easily → they request a short code,
show a QR code on screen, and poll until the user approves on phone/web.

Flow:
  1. TV  → POST /api/device/code          → {device_code, user_code, qr_url}
  2. TV     shows QR + user_code on screen
  3. User → scans QR or visits qr_url (= /activate?code=USER_CODE)
  4. User   logs in (if not already) and taps "Gerät aktivieren"
  5. Web  → POST /api/device/activate      → links user to device_code
  6. TV  → GET  /api/device/token?device_code=… (polling every 3 s)
             returns {status:"pending"} until approved, then {token, refresh_token}

Redis keys:
  device:code:{device_code}  → JSON payload, TTL=900 s
  device:user:{user_code}    → device_code string, TTL=900 s (lookup index)
"""

import json
import secrets
import string
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.core.settings import get_settings
from app.models.user import User
from sqlalchemy import select

router = APIRouter(prefix="/device", tags=["device-auth"])

_TTL = 900          # 15 minutes
_POLL_INTERVAL = 3  # seconds, hint to clients


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


def _make_device_code() -> str:
    return secrets.token_urlsafe(32)


def _make_user_code() -> str:
    """Short human-readable code: 8 uppercase alphanumeric chars, split XXXX-XXXX."""
    alphabet = string.ascii_uppercase + string.digits
    # Remove visually ambiguous chars
    alphabet = alphabet.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


# ── 1. TV requests a code ─────────────────────────────────────────────────────

class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str       # e.g. "ABCD-EFGH" — show on screen
    qr_url: str          # URL to encode as QR
    verification_uri: str
    expires_in: int
    interval: int        # polling interval hint (seconds)


@router.post("/code", response_model=DeviceCodeResponse)
async def request_device_code(request: Request):
    """TV app calls this once. Returns a device_code (secret, for polling) and a
    user_code (short, shown on screen). The TV encodes qr_url as a QR code."""
    r = await _redis()
    device_code = _make_device_code()
    user_code = _make_user_code()

    # Build activation URL — use the request's base URL so it works on any instance
    base = str(request.base_url).rstrip("/")
    qr_url = f"{base}/activate?code={user_code}"

    payload = {
        "device_code": device_code,
        "user_code": user_code,
        "status": "pending",   # pending | approved | denied | expired
        "user_id": None,
        "created_at": int(time.time()),
    }
    pipe = r.pipeline()
    pipe.set(f"device:code:{device_code}", json.dumps(payload), ex=_TTL)
    pipe.set(f"device:user:{user_code}", device_code, ex=_TTL)
    await pipe.execute()
    await r.aclose()

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        qr_url=qr_url,
        verification_uri=f"{base}/activate",
        expires_in=_TTL,
        interval=_POLL_INTERVAL,
    )


# ── 2. Web: activation page (GET) ─────────────────────────────────────────────

@router.get("/activate", response_class=HTMLResponse, include_in_schema=False)
async def activation_page(code: Optional[str] = None):
    """Minimal standalone HTML page — no React bundle needed, works on any browser
    the user opens after scanning the QR. Submits to POST /api/device/activate."""
    code_val = code or ""
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gerät aktivieren – NimtaFlow</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0 }}
  body {{ font-family: -apple-system, system-ui, sans-serif; background: #0f0f13;
         color: #e4e4e7; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; padding: 24px }}
  .card {{ background: #18181b; border: 1px solid #27272a; border-radius: 16px;
           padding: 32px; width: 100%; max-width: 420px; }}
  .logo {{ font-size: 22px; font-weight: 700; color: #a78bfa; margin-bottom: 24px }}
  h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 8px }}
  p  {{ font-size: 14px; color: #a1a1aa; margin-bottom: 24px; line-height: 1.5 }}
  .code-display {{ font-family: monospace; font-size: 28px; font-weight: 700;
                   letter-spacing: 4px; text-align: center; color: #a78bfa;
                   background: #27272a; border-radius: 10px; padding: 14px;
                   margin-bottom: 24px }}
  label {{ font-size: 13px; color: #a1a1aa; display: block; margin-bottom: 6px }}
  input {{ width: 100%; padding: 10px 14px; border-radius: 8px;
           border: 1px solid #3f3f46; background: #27272a; color: #fff;
           font-size: 15px; outline: none; margin-bottom: 16px }}
  input:focus {{ border-color: #7c3aed }}
  button {{ width: 100%; padding: 12px; border-radius: 8px; border: none;
            background: #7c3aed; color: #fff; font-size: 15px; font-weight: 600;
            cursor: pointer }}
  button:hover {{ background: #6d28d9 }}
  .msg {{ margin-top: 16px; text-align: center; font-size: 14px }}
  .ok  {{ color: #34d399 }} .err {{ color: #f87171 }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">✦ NimtaFlow</div>
  <h1>Gerät aktivieren</h1>
  <p>Melde dich an, um das Gerät zu verknüpfen. Der angezeigte Code ist 15 Minuten gültig.</p>
  {"<div class='code-display'>" + code_val + "</div>" if code_val else ""}
  <form id="f">
    <label>Code vom TV-Gerät</label>
    <input id="code" name="code" value="{code_val}" placeholder="ABCD-EFGH" autocomplete="off"
           style="text-transform:uppercase;letter-spacing:2px" maxlength="9" required>
    <label>E-Mail</label>
    <input id="email" type="email" placeholder="deine@email.de" required>
    <label>Passwort</label>
    <input id="pw" type="password" placeholder="••••••••" required>
    <button type="submit">Gerät aktivieren</button>
  </form>
  <div class="msg" id="msg"></div>
</div>
<script>
document.getElementById('code').addEventListener('input', function(e) {{
  let v = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g,'');
  if (v.length > 4) v = v.slice(0,4) + '-' + v.slice(4,8);
  e.target.value = v;
}});
document.getElementById('f').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const btn = e.target.querySelector('button');
  btn.disabled = true; btn.textContent = 'Wird aktiviert…';
  const msg = document.getElementById('msg');
  try {{
    const r = await fetch('/api/device/activate', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{
        user_code: document.getElementById('code').value.trim(),
        email: document.getElementById('email').value.trim(),
        password: document.getElementById('pw').value,
      }})
    }});
    const d = await r.json();
    if (r.ok) {{
      msg.className = 'msg ok';
      msg.textContent = '✓ Gerät aktiviert! Du kannst dieses Fenster schließen.';
      document.getElementById('f').style.display = 'none';
    }} else {{
      msg.className = 'msg err';
      msg.textContent = d.detail || 'Fehler beim Aktivieren.';
      btn.disabled = false; btn.textContent = 'Gerät aktivieren';
    }}
  }} catch(err) {{
    msg.className = 'msg err'; msg.textContent = 'Netzwerkfehler.';
    btn.disabled = false; btn.textContent = 'Gerät aktivieren';
  }}
}});
</script>
</body>
</html>"""
    return HTMLResponse(html)


# ── 3. Web: user approves the device ─────────────────────────────────────────

class ActivateRequest(BaseModel):
    user_code: str
    email: str
    password: str


@router.post("/activate")
async def activate_device(body: ActivateRequest, db: AsyncSession = Depends(get_db)):
    """User submits email+password on the activation page. Validates credentials,
    then marks the device_code as approved with the resulting token."""
    r = await _redis()

    # Look up device_code from user_code
    user_code = body.user_code.upper().strip()
    device_code = await r.get(f"device:user:{user_code}")
    if not device_code:
        await r.aclose()
        raise HTTPException(404, "Code nicht gefunden oder abgelaufen.")

    raw = await r.get(f"device:code:{device_code}")
    if not raw:
        await r.aclose()
        raise HTTPException(404, "Code nicht gefunden oder abgelaufen.")

    payload = json.loads(raw)
    if payload["status"] != "pending":
        await r.aclose()
        raise HTTPException(409, "Code wurde bereits verwendet.")

    # Validate credentials
    result = await db.execute(select(User).where(User.email == body.email.strip()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        await r.aclose()
        raise HTTPException(401, "E-Mail oder Passwort falsch.")

    # Approve: write tokens into the payload
    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    payload["status"] = "approved"
    payload["user_id"] = user.id
    payload["access_token"] = access_token
    payload["refresh_token"] = refresh_token

    # Keep remaining TTL so the TV can still poll
    remaining_ttl = await r.ttl(f"device:code:{device_code}")
    await r.set(f"device:code:{device_code}", json.dumps(payload),
                ex=max(remaining_ttl, 60))
    await r.aclose()

    return {"status": "approved", "message": "Gerät erfolgreich aktiviert."}


# ── 4. TV polls for token ─────────────────────────────────────────────────────

@router.get("/token")
async def poll_token(device_code: str):
    """TV app polls this every ~3 s. Returns status until approved."""
    r = await _redis()
    raw = await r.get(f"device:code:{device_code}")
    await r.aclose()

    if not raw:
        return {"status": "expired"}

    payload = json.loads(raw)
    status = payload["status"]

    if status == "approved":
        return {
            "status": "approved",
            "access_token": payload["access_token"],
            "refresh_token": payload["refresh_token"],
            "token_type": "bearer",
        }
    return {"status": status}  # "pending" | "denied"
