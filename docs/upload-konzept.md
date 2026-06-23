# Konzept: Foto-/Video-Upload in der App → Nutzer-Struktur „Upload/"

## Ziel
Upload aus der iOS-App (und Web) landet **pro Nutzer** in dessen **eigener Ordner-Struktur**
unter einem `Upload/`-Ordner, automatisch nach Datum sortiert, geht durch die normale
Pipeline (Thumbnails/AI/Faces) und respektiert die Per-User-Zugriffsregeln —
**der Nutzer sieht sofort sein eigenes Upload**.

## Problem mit dem Ist-Zustand (`/v1/upload`)
- Speichert nach `/cache/uploads/{hash}{ext}` → **außerhalb** jeder Foto-Quelle (Source-Root).
  → kein sauberes Löschen (`_safe_unlink` löscht nur unter Source-Roots), kein Backup-Scope.
- Endpoint nimmt **keinen `user`** → kein Owner, kein `allow_upload`-Check.
- Pfad `/cache/...` matcht **keine** `folder_whitelist` → ein eingeschränkter User (Demo)
  sieht sein eigenes hochgeladenes Foto nicht (`photo_conditions` filtert es weg).

## Design

### 1. Ziel-Pfad pro Nutzer
Ableitung der „Heimat" aus `access_config`:
- **Eingeschränkter User**: erster Eintrag aus `folder_whitelist` ist die Heimat
  → Ziel = `<whitelist[0]>/Upload/<YYYY>/<YYYY-MM>/`.
  Beispiel Demo (`/photos/Demo`) → `/photos/Demo/Upload/2026/2026-06/IMG_0042.jpg`.
- **Admin / unrestricted**: konfigurierbarer Default (neue Einstellung `upload.default_dir`,
  z.B. `/photos/Upload`) → `/photos/Upload/<YYYY>/<YYYY-MM>/`.
- Optionaler Override pro User: `access_config.upload_dir` (falls jemand einen
  anderen Ablageort will).
- **Invariante (Sicherheit):** Das Ziel MUSS unter einem registrierten Source-Root liegen
  UND (für eingeschränkte User) innerhalb deren `folder_whitelist`. Sonst 400/403.
  Niemals ein vom Client gewählter Pfad — der Server bestimmt das Ziel allein.

### 2. Warum das die Sichtbarkeit „gratis" löst
Zugriff ist ordnerbasiert (`photo_conditions` → `folder_whitelist`-LIKE). Schreiben wir den
Upload **in den Whitelist-Ordner** des Users, ist das Foto für ihn automatisch sichtbar —
**ohne** Per-Foto-ACL. Sauber und konsistent mit dem bestehenden Modell.

### 3. Datei-Ablage
- Datum aus EXIF (`DateTimeOriginal`) → Subordner `YYYY/YYYY-MM`; fehlt EXIF → Upload-Datum.
- Original-Dateiname beibehalten; Kollision → ` (2)`, ` (3)` … anhängen.
- **Dedup** bleibt: SHA-256 vor dem Schreiben; Duplikat → kein zweites File, `status:"duplicate"`.
- Schreiben **atomar**: `.part` → `os.replace` (wie bei Transcodes), damit ein abgebrochener
  Upload keine Torso-Datei hinterlässt.

### 4. Pipeline & DB
- `Photo.path` = finaler Pfad (im Source-Root), nicht `/cache`.
- Nach dem Schreiben `process_photo_task.delay(id)` (Thumbnails/AI/Faces) — wie heute.
- `source_id` auf die passende Quelle setzen, damit Re-Scan/Deletion-Detection es kennt.

### 5. Sicherheit (schließt Audit-Fund M4)
- `user = Depends(current_user_optional)`, unter `enforce` Pflicht-Login.
- Neues Feature-Flag **`allow_upload`** (Default true für Admin; pro User in `access_config`).
  Demo-User: nach Wunsch an/aus.
- Server bestimmt Zielordner aus `user` — Pfad-Traversal unmöglich.
- Größen-/Typ-Limits (z.B. max 2 GB/Datei, nur Bild/Video-MIME).

### 6. iOS-UX (vieles ist schon da: `PhotosPicker` + `uploadFile`)
- Mehrfachauswahl, **Originalqualität** (inkl. Live Photos → JPEG+MOV, Videos).
- **Hintergrund-Upload** mit Fortschritt + Queue/Retry für große Batches
  (URLSession background config, übersteht App-Wechsel).
- Ergebnis-Feedback: „12 hochgeladen, 3 Duplikate übersprungen → Upload/2026-06".
- Optional: „Nach Upload aus Aufnahmen löschen?" (bewusst opt-in).

### 7. Web-Parität
- Drag-&-Drop in die Galerie → derselbe Endpoint, gleiche Ziel-Logik.

### 8. Migration
- Bestehende `/cache/uploads`-Fotos (falls vorhanden) optionaler Move-Job in den
  jeweiligen `Upload/`-Ordner + `path`-Update.

## Umsetzungs-Schritte (klein, deploybar)
1. Backend: `_resolve_upload_dir(user)` (Helper in `core/access.py`), `allow_upload`-Flag,
   `/v1/upload` umbauen (Ziel-Pfad + atomic write + `source_id`), Web-Upload-Endpoint angleichen.
2. Einstellung `upload.default_dir` + Doku.
3. iOS: Background-Upload + besseres Fortschritts-/Ergebnis-UI (Client-Grundgerüst existiert).
4. Verifikation: Demo lädt hoch → landet in `/photos/Demo/Upload/...`, ist für Demo sichtbar,
   NICHT für andere; Admin-Upload nach `/photos/Upload/...`.

## Offene Produktentscheidungen
- **Ordner-Layout:** `Upload/YYYY/YYYY-MM/` (empfohlen) vs. flach `Upload/`.
- **Admin-Default-Ablage:** `/photos/Upload` ok? (oder eigener Source-Root?)
- **Darf der Demo-User überhaupt hochladen?** (für App-Store-Demo evtl. ja, in seinen Ordner.)
