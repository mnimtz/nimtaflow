# NimtaFlow MCP-Server — Konzept

> Ziel: NimtaFlow als MCP-Server, den man in Claude (Desktop/Code) o. a. MCP-Clients
> einbindet, um die eigene Foto-/Video-Bibliothek per natürlicher Sprache zu
> durchsuchen, zu organisieren und **als temporäre Share-Links** auszuliefern.
> Zugriff default **lesend**, optional **schreibend** (Settings-Schalter).

## Grundprinzip

1. **Motor = Metadaten.** Such-Tools fragen ab, was NimtaFlow längst berechnet hat
   (Beschreibung, Personen, Tags, Datum, Ort, CLIP-Embeddings). Der Client „sieht"
   nie 140k Medien — nur die Metadaten von ~10 Treffern als Text.
2. **Thumbnails = seltener Feinschliff.** Nur für die paar Endkandidaten, wenn eine
   *visuelle* Entscheidung nötig ist („welches lacht am schönsten?"). Default-Limit
   klein (~6), damit der Kontext nicht durch Base64 explodiert.
3. **Share-Link = das Ergebnis.** Für „groß ansehen / abspielen / weiterschicken"
   erzeugt der MCP on-demand einen **temporären** Share (bestehendes Share-System,
   share.nimtaflow.com) und liefert den Link als Antwort. Videos/Alben immer so.

## Architektur — dünner Client auf die bestehende API

```
Claude ──MCP──▶ NimtaFlow-MCP-Server ──HTTP + User-Token──▶ FastAPI /api/* ──▶ DB/Services
                 (Tool→API, formatiert                       (ACL, Suche, Shares,
                  Text + Thumbnails + Link)                    Alben — alles vorhanden)
```

- **Kein neuer Geschäftslogik-Code:** Suche (`chat.py`), Shares, Alben, Personen,
  GPS, Reisen, Highlights existieren als API. Der MCP übersetzt Tool↔Endpoint und
  formatiert. Sicherheit/ACL (`photo_conditions(user)`, `visible_person_subquery`)
  wird automatisch geerbt.
- **Deployment:** eigener kleiner Container neben `photoflow-backend-1`
  (z. B. `photoflow-mcp-1`), Python `mcp`-SDK / FastMCP. Auto-Deploy wie der Rest.

## Auth & Sicherheit

- **Pro-User-Token** in der MCP-Client-Config → Server scoped alles auf dieses Konto.
- **Modus-Schalter** Settings: `mcp.mode = read` (Default) / `read_write`.
- **Keine Lösch-/Bulk-GPS-Tools.** GPS nur **einzeln** setzbar (Regel: keine
  Ordner-Massen-Nullung, siehe Memory `gps-no-bulk-folder-cleanup`).
- **MCP-Shares:** kurze TTL (default 24 h, einstellbar), `noindex`.
- **Kein Geburtsdatum/E-Mail in Dateien** (nur Personen-Namen via MWG-Regionen, das
  gibt's schon: `POST /people/write-faces`).

## Tool-Katalog (🔒 = nur bei `mcp.mode=read_write`)

### A · Suche & Stöbern (lesend)
- `suche_medien(query, person?, jahr_von/bis, ort?, typ, nur_favoriten?, limit)`
  → Liste (id, Beschreibung, Personen+Alter, Datum, Ort) + Top-N Thumbnails + opt. Link
- `zaehle_medien(filter)`
- `zeitliche_eckdaten(person, person2?)`  (erstes/letztes Foto)
- `medien_detail(id)`  (volle Metadaten, Personen+Alter, GPS, Tags, Sprachnotiz)
- `aehnliche_finden(id)`  (Embedding-Nachbarn)

### B · Personen (lesend + 🔒)
- `personen_liste` · `person_detail(name)` (Anzahl, Geburtsdatum, Beziehungen)
- `geburtstag_datum(person, alter?)`  (exaktes Datum aus hinterlegtem Geburtsdatum)
- `jahresrueckblick(person, jahr)`
- 🔒 `vorschlaege_bestaetigen(person)` · `gesicht_zuordnen(face_id, person)` · `gesicht_entfernen(face_id)`

### C · Orte & GPS (lesend)
- `orte_liste`  (Städte/Länder + Anzahl)
- `medien_am_ort(ort, radius?)`
- `medien_im_umkreis(lat, lon, km)`  (echte GPS-Radius-Suche)
- `karte_link(filter)`  (Deep-Link Kartenansicht)
- 🔒 `gps_setzen(id, lat, lon)`  — **nur einzeln**

### D · Reisen (lesend + 🔒)
- `reisen_liste` · `reise_detail(id)` (Route, Fotos, Zeitraum)
- 🔒 `reise_erstellen(name, von, bis, foto_ids?)` · `reise_foto_add(reise_id, ids)`

### E · Alben & Teilen  ← Ergebnis-Maschine
- `alben_liste` · `album_detail(id)`
- 🔒 `album_erstellen(name, filter|ids)`
- ⭐ `teilen_link_erstellen(typ=foto|album|auswahl, ziel, ablauf=24h, upload_erlauben?)`
  → temporärer Share-URL = Standard-Antwort auf „zeig/schick mir …"
- 🔒 `postkarte_erstellen(foto_id, text, theme, farbe)` → Bild/Link

### F · Highlights/Video (🔒, budget-bewusst, async)
- `highlights_liste`
- 🔒 `highlight_erstellen(filter, musik_prompt?, animieren?)`
  → läuft asynchron; liefert am Ende Share-Link; respektiert KI-Budget

### G · System (lesend)
- `bibliothek_status`  (Totals, Gesichter zugeordnet/frei, Vorschläge offen, Backlog)
- `verarbeitung_status`

### H · Export (🔒)
- `xmp_schreiben(person|auswahl)`  → MWG-Gesichtsregionen in Dateien (bestehender Export)

## Typischer Ablauf

> „Schick mir die schönsten Strandfotos von Lea aus 2022"
> 1. `suche_medien("Strand", person=Lea, jahr=2022)` → 30 Treffer als Text
> 2. (optional) Top 8 Thumbnails → 5 schönste visuell wählen
> 3. `teilen_link_erstellen(typ=auswahl, ziel=[5 ids], ablauf=24h)` → 🔗 Link
> → Antwort: 5 Vorschau-Thumbnails + „▶ Hier ansehen/teilen (läuft in 24 h ab)"

## Bau-Phasen

- **Ph0 — Skelett:** MCP-Container, Token-Auth, 1 Tool `suche_medien` (Text+Thumbnails).
  Beweist Transport + „Client sieht Treffer".
- **Ph1 — Lese-Suite:** Suche/Detail/Count/Personen/Orte+GPS/Alben/Status.
- **Ph2 — Share-Link-Deliverable** + TTL-Shares.
- **Ph3 — Schreib-Suite** hinter `mcp.mode=read_write` (Favorit, Bewertung, Album,
  Gesicht, Vorschläge, XMP).
- **Ph4 — Async/kostenbewusst:** Highlights/Video, GPS-Einzel, Postkarte.

## Offene Entscheidungen

- Token-Ausgabe/Rotation (eigener „MCP-Token" pro User in Settings?).
- Thumbnail-Default-Anzahl & Max-Bytes pro Antwort.
- Soll `teilen_link_erstellen` Shares in der normalen Share-Verwaltung sichtbar
  machen (mit „via MCP"-Label) oder unsichtbar/auto-aufräumen?
