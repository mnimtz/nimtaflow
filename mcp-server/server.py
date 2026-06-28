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
import base64
import asyncio

import httpx
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent, ImageContent

API = os.environ.get("NIMTAFLOW_API_URL", "http://backend:8000").rstrip("/")
ENV_TOKEN = os.environ.get("NIMTAFLOW_TOKEN")          # optionaler Fallback (lokal/Single-User)
MAX_THUMBS = int(os.environ.get("MCP_MAX_THUMBS", "6"))
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8000"))

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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
