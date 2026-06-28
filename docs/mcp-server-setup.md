# NimtaFlow MCP-Server — Einrichtung

> Verbinde Claude, ChatGPT oder andere MCP-Clients mit deiner eigenen NimtaFlow-Bibliothek
> und durchsuche bzw. organisiere sie in natürlicher Sprache.
> Konzept & Hintergrund: **[mcp-server-konzept.md](mcp-server-konzept.md)**.

## Was ist das?

Der MCP-Server (`mcp-server/`, FastMCP, Streamable-HTTP) macht NimtaFlow zu einem
**Model-Context-Protocol-Server**. Ein KI-Assistent (Claude, ChatGPT, …) kann darüber
deine Mediathek durchsuchen und bearbeiten — z. B. *„Schick mir die schönsten
Strandfotos von Lea aus 2022"*.

Wichtig:

- Der Assistent sieht **nie** deine ganze Bibliothek — nur die Metadaten der wenigen
  Treffer als Text, plus (bei Bedarf) ein paar Vorschau-Thumbnails, die er wirklich
  *sehen* kann.
- Alles läuft über **deinen persönlichen Bearer-Token** und **erbt exakt die ACL
  dieses Kontos** (gleiche Rechte wie in der API: sichtbare Ordner/Personen/Zeiträume).
- Ergebnisse zum Ansehen/Weiterschicken werden als **temporäre Share-Links**
  ausgeliefert, die **automatisch ablaufen**.
- Standardmäßig **nur lesend**; Schreib-Tools schaltest du bewusst per Schalter frei.

## Einschalten & Token erzeugen

1. In NimtaFlow: **Einstellungen → MCP**.
2. MCP-Server **einschalten** (on/off).
3. Modus wählen: **`read`** (nur lesen, Default) oder **`read_write`** (auch schreiben).
4. **Token erzeugen** — das ist dein persönlicher Bearer-Token. Kopiere ihn sofort
   und bewahre ihn sicher auf (er gilt für genau dein Konto).

## Connector-URL

```
http://DEIN-SERVER:8091/mcp
```

- Ersetze `DEIN-SERVER` durch Hostname oder Adresse deiner NimtaFlow-Instanz
  (z. B. `https://fotos.example.com:8091/mcp`).
- **Port 8091 muss erreichbar sein** (Firewall/Reverse-Proxy entsprechend öffnen).
- Authentifizierung: **HTTP-Header** `Authorization: Bearer DEIN-TOKEN`.

## Einbinden in einen MCP-Client

Der statische Bearer-Token funktioniert **überall, wo man HTTP-Header setzen kann**:

- **Claude Desktop** — über die MCP-Server-Konfiguration (`Authorization`-Header
  mit `Bearer DEIN-TOKEN` für die Streamable-HTTP-URL).
- **ChatGPT (API / Responses)** — MCP-Tool mit `headers: { "Authorization": "Bearer DEIN-TOKEN" }`.
- **MCP Inspector** — URL eintragen, im Header-Feld den Bearer-Token setzen (gut zum Testen).

## OAuth-Connector (Ein-Klick in Claude/ChatGPT)

Der MCP-Server ist zugleich ein **OAuth-2.1-Authorization-Server** (Dynamic Client
Registration + PKCE). Die gehosteten „Custom-Connector"-Dialoge von claude.ai bzw.
ChatGPT funktionieren damit **ohne manuelles Token-Kopieren**: Du trägst nur die
Connector-URL ein, klickst „Verbinden/Autorisieren", **meldest dich einmal mit deinem
NimtaFlow-Konto an** (Consent-Seite), und der Client bekommt automatisch ein Token.

Voraussetzungen dafür:
- Der MCP-Server muss **öffentlich per HTTPS** erreichbar sein (z. B. `https://mcp.deinedomain.de`
  über denselben Cloudflare-Tunnel/Reverse-Proxy wie die App). OAuth-Clients verlangen HTTPS.
- Env **`MCP_PUBLIC_URL`** auf genau diese externe Basis-URL setzen (für Discovery/Redirects).
- Env **`SECRET_KEY`** = dasselbe Secret wie das Backend (ist im Compose bereits gesetzt) —
  dadurch ist der ausgestellte OAuth-Token ein gültiges NimtaFlow-JWT.

Ist `MCP_PUBLIC_URL` nicht gesetzt, läuft OAuth nur lokal (`http://localhost:8091`); der
**statische Token-Weg oben funktioniert unabhängig davon immer weiter**.

## Die 14 Tools

Such- und Lese-Tools (immer verfügbar):

1. **`suche_medien`** — semantische Suche; liefert Text-Treffer + ein paar Thumbnails, die der Assistent wirklich sehen kann.
2. **`medien_detail`** — volle Metadaten eines Fotos/Videos, inkl. Alter jeder erkannten Person zum Aufnahmedatum.
3. **`alben_liste`** — listet alle Alben mit Foto-Anzahl und Typ (manuell/smart).
4. **`personen_liste`** — listet die erfassten Personen mit Foto-Anzahl und (falls vorhanden) Geburtsdatum.
5. **`orte_liste`** — listet Orte (Städte/Länder) mit Foto-Anzahl.
6. **`medien_im_umkreis`** — echte GPS-Radius-Suche um Koordinaten herum.
7. **`bibliothek_status`** — Status der Bibliothek (Totals, zugeordnete/freie Gesichter, offene Vorschläge, Backlog).
8. **`teilen_link_erstellen`** — erzeugt einen temporären Share-Link (einzelnes Foto / Album / freie Auswahl → automatisch als Album); läuft automatisch ab.

Schreib-Tools (nur im Modus `read_write`):

9. **`favorit_setzen`** — markiert ein Foto als Favorit (oder entfernt die Markierung).
10. **`bewertung_setzen`** — setzt die Sterne-Bewertung (0–5) eines Fotos.
11. **`album_erstellen`** — legt ein Album an (optional gleich mit Foto-IDs befüllt).
12. **`gesicht_zuordnen`** — ordnet ein Gesicht (face_id) einer Person zu.
13. **`gesicht_entfernen`** — entfernt die Personen-Zuordnung eines Gesichts.
14. **`vorschlaege_bestaetigen`** — bestätigt die offenen Gesichts-Vorschläge einer Person.

## Sicherheit auf einen Blick

- **Read/Read_write-Schalter** (Einstellungen → MCP): im Default-Modus `read` sind
  alle Schreib-Tools gesperrt; erst `read_write` gibt Favorit/Bewertung/Album/
  Gesicht/Vorschläge frei. Lösch- oder Bulk-Tools gibt es bewusst nicht.
- **ACL-Vererbung:** Der Token ist an dein Konto gebunden — der Assistent sieht und
  ändert **nur**, was du selbst sehen/ändern darfst.
- **Share-Links laufen automatisch ab** und sind nicht erratbar — geteiltes bleibt
  zeitlich begrenzt.
