"""NimtaFlow MCP-Server — Phase 0.

Dünner Client auf die bestehende NimtaFlow-/api. Stellt MCP-Tools bereit, die ein
MCP-Client (Claude Desktop/Code etc.) aufrufen kann. Auth: Bearer-Token kommt aus
der MCP-Anfrage (oder Fallback env NIMTAFLOW_TOKEN) und wird unverändert an die /api
durchgereicht → ACL/Sichtbarkeit der NimtaFlow-Instanz gelten automatisch.

Phase 0 = ein Tool `suche_medien` (semantische Suche → Text + Thumbnails). Weitere
Tools (Detail, Alben, Teilen-Link, Schreiben) folgen laut docs/mcp-server-konzept.md.

Transport: Streamable HTTP unter /mcp. Connector-URL: http://<host>:<MCP_PORT>/mcp
"""
import os
import time
import html
import base64
import asyncio
import math
import secrets as _secrets
from datetime import date

import httpx
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent, ImageContent

API = os.environ.get("NIMTAFLOW_API_URL", "http://backend:8000").rstrip("/")
ENV_TOKEN = os.environ.get("NIMTAFLOW_TOKEN")          # optionaler Fallback (lokal/Single-User)
MAX_THUMBS = int(os.environ.get("MCP_MAX_THUMBS", "6"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8000"))

# ── OAuth 2.1 (optional) ─────────────────────────────────────────────────────────
# Aktiv, sobald SECRET_KEY gesetzt ist (= dasselbe Secret wie das Backend). Dann ist
# der MCP-Server ein vollwertiger OAuth-Authorization-Server: Claude/ChatGPT können
# ihn als Ein-Klick-Connector einbinden (DCR + PKCE + Login-Consent). Der ausgestellte
# Access-Token IST ein langlebiges NimtaFlow-JWT → die Tools reichen ihn an /api durch
# (erbt ACL) und der STATISCHE Token (Settings → MCP) bleibt parallel gültig.
SECRET = os.environ.get("SECRET_KEY", "")
ALG = os.environ.get("ALGORITHM", "HS256")
PUBLIC_URL = os.environ.get("MCP_PUBLIC_URL", f"http://localhost:{PORT}").rstrip("/")
OAUTH = bool(SECRET)

if OAUTH:
    from jose import jwt, JWTError
    from starlette.routing import Route
    from starlette.responses import HTMLResponse, RedirectResponse
    from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
    from mcp.server.auth.provider import (
        OAuthAuthorizationServerProvider, AuthorizationParams, AuthorizationCode,
        AccessToken, RefreshToken, construct_redirect_uri,
    )
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

    _TEN_YEARS = 3650 * 24 * 3600

    def _mint(sub: str) -> str:
        return jwt.encode({"sub": str(sub), "exp": int(time.time()) + _TEN_YEARS}, SECRET, algorithm=ALG)

    class NimtaProvider(OAuthAuthorizationServerProvider):
        """In-memory OAuth AS. Authentifizierung = NimtaFlow-Login (Consent-Seite)."""
        def __init__(self):
            self.clients: dict = {}
            self.codes: dict = {}
            self.pending: dict = {}   # rid -> (client_id, AuthorizationParams)

        async def get_client(self, client_id):
            return self.clients.get(client_id)

        async def register_client(self, client_info):
            self.clients[client_info.client_id] = client_info

        async def authorize(self, client, params):
            rid = _secrets.token_urlsafe(16)
            self.pending[rid] = (client.client_id, params)
            return f"{PUBLIC_URL}/oauth/consent?rid={rid}"

        async def load_authorization_code(self, client, authorization_code):
            c = self.codes.get(authorization_code)
            return c if (c and c.client_id == client.client_id) else None

        async def exchange_authorization_code(self, client, authorization_code):
            self.codes.pop(authorization_code.code, None)
            access = _mint(authorization_code.subject)
            return OAuthToken(access_token=access, token_type="Bearer",
                              expires_in=_TEN_YEARS, scope="nimtaflow")

        async def load_access_token(self, token):
            try:
                payload = jwt.decode(token, SECRET, algorithms=[ALG])
            except JWTError:
                return None
            return AccessToken(token=token, client_id="nimtaflow", scopes=["nimtaflow"],
                               expires_at=payload.get("exp"), subject=str(payload.get("sub", "")))

        async def load_refresh_token(self, client, refresh_token):
            return None

        async def exchange_refresh_token(self, client, refresh_token, scopes):
            raise NotImplementedError("refresh not supported (tokens are long-lived)")

        async def revoke_token(self, token):
            return None

    _provider = NimtaProvider()

    async def _oauth_consent(request):
        """GET: Login-Formular. POST: NimtaFlow-Login prüfen → Auth-Code → Redirect."""
        if request.method == "GET":
            rid = request.query_params.get("rid", "")
            err = request.query_params.get("err", "")
            msg = "<p style='color:#c0392b'>Login fehlgeschlagen.</p>" if err else ""
            body = f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
            <title>NimtaFlow – Zugriff erlauben</title>
            <body style="font-family:system-ui;max-width:380px;margin:8vh auto;padding:0 20px;background:#1b1a18;color:#eee">
            <h2 style="color:#e8b54a">NimtaFlow verbinden</h2>
            <p style="color:#aaa;font-size:14px">Melde dich mit deinem NimtaFlow-Konto an, um dem KI-Assistenten Zugriff auf deine Mediathek zu erlauben.</p>{msg}
            <form method="post" action="/oauth/consent">
              <input type="hidden" name="rid" value="{html.escape(rid)}">
              <input name="email" type="email" placeholder="E-Mail" required style="width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #444;background:#2a2826;color:#eee">
              <input name="password" type="password" placeholder="Passwort" required style="width:100%;padding:10px;margin:6px 0;border-radius:8px;border:1px solid #444;background:#2a2826;color:#eee">
              <button type="submit" style="width:100%;padding:11px;margin-top:10px;border:0;border-radius:8px;background:#e8b54a;color:#1b1a18;font-weight:600;cursor:pointer">Zugriff erlauben</button>
            </form></body>"""
            return HTMLResponse(body)

        form = await request.form()
        rid = form.get("rid", "")
        entry = _provider.pending.get(rid, None)
        if not entry:
            return HTMLResponse("<p>Sitzung abgelaufen – bitte neu starten.</p>", status_code=400)
        client_id, params = entry
        # NimtaFlow-Login prüfen
        try:
            async with httpx.AsyncClient(base_url=API, timeout=20) as c:
                r = await c.post("/api/auth/login",
                                 data={"username": form.get("email", ""), "password": form.get("password", "")})
            if r.status_code != 200:
                raise ValueError("login failed")
            sub = jwt.get_unverified_claims(r.json()["access_token"]).get("sub")
        except Exception:
            self_rid = html.escape(rid)
            return RedirectResponse(f"/oauth/consent?rid={self_rid}&err=1", status_code=303)
        # Login erfolgreich — Sitzung jetzt verbrauchen
        _provider.pending.pop(rid, None)
        # Auth-Code ausstellen
        code = _secrets.token_urlsafe(24)
        self_code = AuthorizationCode(
            code=code, scopes=params.scopes or ["nimtaflow"], expires_at=int(time.time()) + 300,
            client_id=client_id, code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject=str(sub),
        )
        _provider.codes[code] = self_code
        return RedirectResponse(
            construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state),
            status_code=303)

    _auth_settings = AuthSettings(
        issuer_url=PUBLIC_URL,
        resource_server_url=PUBLIC_URL,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=["nimtaflow"], default_scopes=["nimtaflow"]),
        required_scopes=[],
    )
    mcp = FastMCP("NimtaFlow", host=HOST, port=PORT,
                  auth_server_provider=_provider, auth=_auth_settings)
else:
    mcp = FastMCP("NimtaFlow", host=HOST, port=PORT)


def _token_from_ctx(ctx: Context | None) -> str | None:
    """Bearer-Token aus der eingehenden MCP-HTTP-Anfrage ziehen (sonst env-Fallback)."""
    try:
        req = ctx.request_context.request  # Starlette-Request bei HTTP-Transport
        auth = req.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
    except Exception:
        pass
    return ENV_TOKEN


async def _get_json(client: httpx.AsyncClient, path: str, params: dict | None = None):
    r = await client.get(path, params=params)
    r.raise_for_status()
    return r.json()


class _Disabled(Exception):
    """MCP ist abgeschaltet oder Token ungültig — Botschaft an den Client."""


async def _status(client: httpx.AsyncClient) -> dict:
    """Liest den An/Aus-Schalter + Modus + Share-TTL. Wirft _Disabled mit Klartext."""
    try:
        st = await _get_json(client, "/api/settings/mcp-status")
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            raise _Disabled("Nicht autorisiert — bitte einen gültigen MCP-Token im Connector hinterlegen (Einstellungen → MCP → Token erzeugen).")
        raise
    if not st.get("enabled"):
        raise _Disabled("Der MCP-Zugriff ist in NimtaFlow gerade deaktiviert (Einstellungen → MCP → einschalten).")
    return st


def _write_guard(st: dict):
    if st.get("mode") != "read_write":
        raise _Disabled("Schreibzugriff ist aus. In NimtaFlow unter Einstellungen → MCP den Modus auf „lesend + schreibend“ stellen.")


def _age(birthdate: str | None, taken_at: str | None) -> int | None:
    if not birthdate or not taken_at:
        return None
    try:
        bd = date.fromisoformat(birthdate[:10]); sd = date.fromisoformat(taken_at[:10])
    except Exception:
        return None
    a = sd.year - bd.year - ((sd.month, sd.day) < (bd.month, bd.day))
    return a if 0 <= a < 130 else None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


@mcp.tool(
    description=(
        "Durchsucht die NimtaFlow-Foto- und Videobibliothek semantisch (über die schon "
        "berechneten KI-Beschreibungen, erkannten Personen, Tags, Datum und Ort) und gibt "
        "die besten Treffer als Liste (mit #ID, Datum, Personen, Ort, Beschreibung) plus "
        "einige Vorschau-Thumbnails zurück. Beispiele: 'Lea am Strand 2022', "
        "'Geburtstag mit Kuchen', 'Sonnenuntergang am Meer'."
    )
)
async def suche_medien(query: str, limit: int = 12, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    limit = max(1, min(int(limit), 40))

    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            await _status(client)   # An/Aus-Schalter + Auth respektieren
        except _Disabled as e:
            return str(e)

        page = await _get_json(client, "/api/v1/search", {"q": query, "limit": limit})
        items = page.get("items", [])
        if not items:
            return f"Keine Treffer für „{query}“."

        # Treffer mit Detail (Beschreibung/Personen/Ort) anreichern — begrenzt.
        async def detail(pid: int):
            try:
                return await _get_json(client, f"/api/photos/{pid}")
            except Exception:
                return {}

        details = await asyncio.gather(*(detail(it["id"]) for it in items))

        lines = [f"{len(items)} Treffer für „{query}“:"]
        for i, (it, d) in enumerate(zip(items, details), 1):
            # pro Person nur einmal (eine Collage hat mehrere Gesichter derselben Person)
            people = ", ".join(dict.fromkeys(p["name"] for p in d.get("people", []) if p.get("name")))
            place = ", ".join(x for x in (d.get("city"), d.get("country")) if x)
            desc = (d.get("description") or d.get("ai_description") or "").strip().replace("\n", " ")
            date = (it.get("taken_at") or "")[:10]
            typ = "🎬" if it.get("is_video") else "📷"
            meta = " · ".join(x for x in [date, people, place] if x)
            lines.append(f"{i}. {typ} #{it['id']} {meta}" + (f" — {desc[:160]}" if desc else ""))

        contents: list = [TextContent(type="text", text="\n".join(lines))]

        # Thumbnails der ersten MAX_THUMBS (damit der Kontext nicht explodiert).
        async def thumb(pid: int):
            try:
                r = await client.get(f"/api/photos/{pid}/thumbnail", params={"size": "small"})
                r.raise_for_status()
                mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
                return ImageContent(type="image", mimeType=mime,
                                    data=base64.b64encode(r.content).decode())
            except Exception:
                return None

        thumbs = await asyncio.gather(*(thumb(it["id"]) for it in items[:MAX_THUMBS]))
        contents.extend([t for t in thumbs if t])
        return contents


@mcp.tool(
    description=(
        "Erzeugt einen temporären, login-freien Teilen-Link für ein einzelnes Foto/Video "
        "(typ='foto', foto_id), ein bestehendes Album (typ='album', album_id) oder eine "
        "freie Auswahl mehrerer Medien (typ='auswahl', foto_ids=[...] — legt dafür ein "
        "Album an und teilt es). Der Link läuft automatisch ab (Standard aus den "
        "NimtaFlow-Einstellungen). Nutze das als Ergebnis auf 'zeig/schick mir …', um "
        "Großansicht, Videowiedergabe oder Weitergeben zu ermöglichen. IDs kommen aus "
        "suche_medien (#ID)."
    )
)
async def teilen_link_erstellen(
    typ: str,
    foto_id: int = None,
    album_id: int = None,
    foto_ids: list[int] = None,
    titel: str = None,
    ablauf_stunden: int = None,
    ctx: Context = None,
):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60) as client:
        try:
            st = await _status(client)
        except _Disabled as e:
            return str(e)

        ttl_h = int(ablauf_stunden or st.get("share_ttl_hours") or 24)
        expires_days = max(1, round(ttl_h / 24))

        async def _post(path, payload):
            r = await client.post(path, json=payload)
            r.raise_for_status()
            return r.json()

        try:
            if typ == "foto":
                if not foto_id:
                    return "Für typ='foto' bitte foto_id angeben."
                share = await _post("/api/shares", {
                    "share_type": "photo", "photo_id": int(foto_id),
                    "title": titel, "expires_days": expires_days})
                label = f"Foto #{foto_id}"

            elif typ == "album":
                if not album_id:
                    return "Für typ='album' bitte album_id angeben."
                share = await _post("/api/shares", {
                    "share_type": "album", "album_id": int(album_id),
                    "title": titel, "expires_days": expires_days})
                label = f"Album #{album_id}"

            elif typ == "auswahl":
                ids = [int(i) for i in (foto_ids or [])]
                if not ids:
                    return "Für typ='auswahl' bitte foto_ids=[…] angeben."
                name = (titel or "Auswahl") + " – via MCP geteilt"
                album = await _post("/api/albums", {"name": name, "album_type": "manual"})
                aid = album["id"]
                await _post(f"/api/albums/{aid}/photos", {"photo_ids": ids})
                share = await _post("/api/shares", {
                    "share_type": "album", "album_id": aid,
                    "title": titel or "Auswahl", "expires_days": expires_days})
                label = f"{len(ids)} Medien"

            else:
                return "Unbekannter typ — erlaubt: 'foto', 'album', 'auswahl'."
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            return f"Teilen fehlgeschlagen ({e.response.status_code}): {detail or e.response.text[:120]}"

        url = share.get("url")
        return (f"🔗 Teilen-Link für {label}: {url}\n"
                f"Läuft in ~{expires_days} Tag(en) ab. "
                f"Login-frei – zum Ansehen/Abspielen/Weitergeben.")


# ── Lese-Tools ──────────────────────────────────────────────────────────────────

@mcp.tool(description=(
    "Alle Details zu einem Foto/Video (#ID): Datum, Ort, erkannte Personen (mit Alter "
    "zum Aufnahmezeitpunkt, falls Geburtsdatum hinterlegt), Tags, KI-Beschreibung, "
    "GPS, Favorit, Bewertung."))
async def medien_detail(foto_id: int, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        try:
            d = await _get_json(client, f"/api/photos/{int(foto_id)}")
        except httpx.HTTPStatusError as e:
            return f"Foto #{foto_id} nicht gefunden ({e.response.status_code})."
        taken = d.get("taken_at")
        ppl = []
        seen = set()
        for p in d.get("people", []):
            nm = p.get("name")
            if not nm or nm in seen:
                continue
            seen.add(nm)
            age = _age(p.get("birthdate"), taken)
            ppl.append(f"{nm}" + (f" ({age} J.)" if age is not None else ""))
        place = ", ".join(x for x in (d.get("city"), d.get("country"), d.get("location_name")) if x)
        lines = [f"{'🎬' if d.get('is_video') else '📷'} #{d.get('id')} — {d.get('filename','')}"]
        if taken: lines.append(f"Datum: {taken[:19].replace('T',' ')}")
        if place: lines.append(f"Ort: {place}")
        if ppl: lines.append(f"Personen: {', '.join(ppl)}")
        if d.get("tags"): lines.append(f"Tags: {', '.join(d['tags'])}")
        if d.get("latitude") is not None: lines.append(f"GPS: {d['latitude']:.5f}, {d['longitude']:.5f}")
        if d.get("user_rating"): lines.append(f"Bewertung: {'★'*int(d['user_rating'])}")
        if d.get("is_favorite"): lines.append("⭐ Favorit")
        desc = (d.get("description") or "").strip()
        if desc: lines.append(f"\nBeschreibung: {desc}")
        return "\n".join(lines)


@mcp.tool(description="Listet alle Alben mit Foto-Anzahl und Typ (manuell/smart).")
async def alben_liste(ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        albums = await _get_json(client, "/api/albums")
        if not albums:
            return "Noch keine Alben."
        rows = sorted(albums, key=lambda a: a.get("photo_count", 0), reverse=True)
        return "Alben:\n" + "\n".join(
            f"• #{a['id']} {a['name']} — {a.get('photo_count',0)} Medien ({a.get('album_type','?')})"
            for a in rows)


@mcp.tool(description="Listet die erfassten Personen mit Foto-Anzahl und (falls vorhanden) Geburtsdatum.")
async def personen_liste(ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        people = await _get_json(client, "/api/people")
        named = [p for p in people if (p.get("name") or "").strip() and not p.get("is_hidden")]
        rows = sorted(named, key=lambda p: p.get("photo_count", 0), reverse=True)[:80]
        return "Personen:\n" + "\n".join(
            f"• #{p['id']} {p['name']} — {p.get('photo_count',0)} Fotos"
            + (f", geb. {p['birthdate']}" if p.get("birthdate") else "")
            for p in rows)


@mcp.tool(description="Listet die Orte (Städte/Länder) mit Foto-Anzahl — woher die meisten Aufnahmen stammen.")
async def orte_liste(ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        rows = await _get_json(client, "/api/photos/map")
        counts: dict = {}
        for r in rows:
            place = ", ".join(x for x in (r.get("city"), r.get("country")) if x)
            if place:
                counts[place] = counts.get(place, 0) + 1
        if not counts:
            return "Keine Orte mit GPS/Stadt gefunden."
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:40]
        return f"Orte ({len(counts)} gesamt, Top 40):\n" + "\n".join(f"• {p} — {n}" for p, n in top)


@mcp.tool(description=(
    "Findet Fotos/Videos im Umkreis (km) um eine GPS-Koordinate. Liefert die nächsten "
    "Treffer mit Entfernung, Ort und Datum."))
async def medien_im_umkreis(lat: float, lon: float, km: float = 5.0, limit: int = 20, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        rows = await _get_json(client, "/api/photos/map")
        hits = []
        for r in rows:
            la, lo = r.get("latitude"), r.get("longitude")
            if la is None or lo is None:
                continue
            dist = _haversine_km(float(lat), float(lon), float(la), float(lo))
            if dist <= float(km):
                hits.append((dist, r))
        hits.sort(key=lambda x: x[0])
        if not hits:
            return f"Keine Medien im Umkreis von {km} km um {lat:.4f}, {lon:.4f}."
        out = [f"{len(hits)} Treffer im Umkreis von {km} km (Top {min(limit,len(hits))}):"]
        for dist, r in hits[:int(limit)]:
            place = ", ".join(x for x in (r.get("city"), r.get("country")) if x)
            out.append(f"• {'🎬' if r.get('is_video') else '📷'} #{r['id']} — {dist:.1f} km" + (f" · {place}" if place else ""))
        return "\n".join(out)


@mcp.tool(description=(
    "Überblick über die Bibliothek: Gesamtzahl Fotos/Videos/Favoriten, Zeitspanne, "
    "Gesichter (zugeordnet/frei), und der Verarbeitungs-Rückstand."))
async def bibliothek_status(ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            await _status(client)
        except _Disabled as e:
            return str(e)
        stats = await _get_json(client, "/api/photos/stats")
        try:
            remote = await _get_json(client, "/api/remote/status")
        except Exception:
            remote = {}
        lines = ["📊 Bibliothek:"]
        if stats.get("total") is not None: lines.append(f"• Fotos (fertig): {stats['total']:,}".replace(",", "."))
        if stats.get("videos") is not None: lines.append(f"• Videos: {stats['videos']:,}".replace(",", "."))
        if stats.get("favorites") is not None: lines.append(f"• Favoriten: {stats['favorites']:,}".replace(",", "."))
        if stats.get("with_gps") is not None: lines.append(f"• mit GPS: {stats['with_gps']:,}".replace(",", "."))
        if stats.get("min_date") and stats.get("max_date"):
            lines.append(f"• Zeitspanne: {str(stats['min_date'])[:10]} … {str(stats['max_date'])[:10]}")
        ft, fa, fu = remote.get("faces_total"), remote.get("faces_assigned"), remote.get("faces_unassigned")
        if ft is not None:
            lines.append(f"• Gesichter: {ft:,} gesamt, {fa:,} zugeordnet, {fu:,} frei".replace(",", "."))
        if remote.get("pending") is not None:
            lines.append(f"• Beschreibungs-Rückstand: {remote['pending']:,}".replace(",", "."))
        return "\n".join(lines)


# ── Schreib-Tools (nur bei mcp.mode = read_write) ────────────────────────────────

@mcp.tool(description=(
    "Markiert ein Foto/Video als Favorit oder hebt die Markierung auf. "
    "Nur bei aktiviertem Schreibmodus."))
async def favorit_setzen(foto_id: int, favorit: bool = True, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        d = await _get_json(client, f"/api/photos/{int(foto_id)}")
        if bool(d.get("is_favorite")) == bool(favorit):
            return f"#{foto_id} ist bereits {'Favorit' if favorit else 'kein Favorit'}."
        r = await client.patch(f"/api/photos/{int(foto_id)}/favorite")
        r.raise_for_status()
        return f"#{foto_id} ist jetzt {'⭐ Favorit' if r.json().get('is_favorite') else 'kein Favorit'}."


@mcp.tool(description="Setzt die Sterne-Bewertung (0–5) eines Fotos. Nur bei aktiviertem Schreibmodus.")
async def bewertung_setzen(foto_id: int, sterne: int, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        r = await client.patch(f"/api/photos/{int(foto_id)}/rating", params={"rating": max(0, min(5, int(sterne)))})
        r.raise_for_status()
        return f"#{foto_id} Bewertung: {'★'*int(r.json().get('user_rating',0)) or '—'}"


@mcp.tool(description=(
    "Legt ein neues manuelles Album an, optional gleich mit Fotos (foto_ids). "
    "Nur bei aktiviertem Schreibmodus."))
async def album_erstellen(name: str, foto_ids: list[int] = None, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        r = await client.post("/api/albums", json={"name": name, "album_type": "manual"})
        r.raise_for_status()
        album = r.json(); aid = album["id"]
        n = 0
        ids = [int(i) for i in (foto_ids or [])]
        if ids:
            rr = await client.post(f"/api/albums/{aid}/photos", json={"photo_ids": ids})
            rr.raise_for_status(); n = rr.json().get("added", len(ids))
        return f"Album „{name}“ (#{aid}) angelegt" + (f", {n} Medien hinzugefügt." if ids else ".")


@mcp.tool(description=(
    "Ordnet ein erkanntes Gesicht (face_id) einer Person (person_id) zu. "
    "Nur bei aktiviertem Schreibmodus."))
async def gesicht_zuordnen(face_id: int, person_id: int, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        r = await client.post(f"/api/people/faces/{int(face_id)}/assign/{int(person_id)}")
        r.raise_for_status()
        return f"Gesicht {face_id} → Person {person_id} zugeordnet."


@mcp.tool(description=(
    "Setzt GPS-Koordinaten (Breitengrad, Längengrad, optional Höhe in Metern) für ein "
    "einzelnes Foto/Video. Nützlich wenn das Bild keine GPS-Daten hat oder die vorhandenen "
    "korrigiert werden sollen. Nur bei aktiviertem Schreibmodus."))
async def gps_setzen(foto_id: int, breitengrad: float, laengengrad: float,
                     hoehe_m: float = None, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        payload: dict = {"latitude": float(breitengrad), "longitude": float(laengengrad)}
        if hoehe_m is not None:
            payload["altitude"] = float(hoehe_m)
        try:
            r = await client.patch(f"/api/photos/{int(foto_id)}/meta", json=payload)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            return f"GPS setzen fehlgeschlagen ({e.response.status_code}): {detail or e.response.text[:120]}"
        return (f"#{foto_id} GPS gesetzt: {breitengrad:.6f}, {laengengrad:.6f}"
                + (f", Höhe {hoehe_m:.1f} m" if hoehe_m is not None else "") + ".")


@mcp.tool(description="Entfernt die Personen-Zuordnung eines Gesichts (face_id). Nur bei aktiviertem Schreibmodus.")
async def gesicht_entfernen(face_id: int, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=30) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        r = await client.delete(f"/api/people/faces/{int(face_id)}/unassign")
        r.raise_for_status()
        return f"Zuordnung von Gesicht {face_id} entfernt."


@mcp.tool(description=(
    "Bestätigt ALLE offenen Gesichts-Vorschläge für eine Person (person_id) auf einmal "
    "— die vorgeschlagenen Gesichter werden ihr zugeordnet. Nur bei aktiviertem Schreibmodus."))
async def vorschlaege_bestaetigen(person_id: int, ctx: Context = None):
    token = _token_from_ctx(ctx)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=API, headers=headers, timeout=60) as client:
        try:
            st = await _status(client); _write_guard(st)
        except _Disabled as e:
            return str(e)
        r = await client.post(f"/api/people/suggestions/confirm/{int(person_id)}")
        r.raise_for_status()
        data = r.json() if r.content else {}
        n = data.get("confirmed", data.get("count", "?"))
        return f"Vorschläge für Person {person_id} bestätigt ({n})."


if __name__ == "__main__":
    if OAUTH:
        import uvicorn
        app = mcp.streamable_http_app()
        app.router.routes.append(Route("/oauth/consent", _oauth_consent, methods=["GET", "POST"]))
        uvicorn.run(app, host=HOST, port=PORT)
    else:
        mcp.run(transport="streamable-http")
