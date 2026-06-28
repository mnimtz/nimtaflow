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
        # An/Aus-Schalter respektieren
        try:
            st = await _get_json(client, "/api/settings/mcp-status")
            if not st.get("enabled"):
                return "Der MCP-Zugriff ist in NimtaFlow gerade deaktiviert (Einstellungen → MCP → einschalten)."
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                return "Nicht autorisiert — bitte einen gültigen MCP-Token im Connector hinterlegen (Einstellungen → MCP → Token erzeugen)."
            raise

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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
