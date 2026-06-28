# Konzept: Push-Nachrichten & Release-Readiness-Audit

> Roadmap-Punkt #8 (finaler Block). Konzept/Checkliste — kein Code.
> Erstellt 2026-06-22.

---

## Teil A — Push-Nachrichten

### Wofür Pushes (Anwendungsfälle, nach Wert sortiert)
PhotoFlow-Ereignisse, die eine Benachrichtigung wert sind:
1. **„Highlight der Woche" fertig** — der wöchentliche Auto-Highlight ist gerendert.
2. **KI-Szene fertig** — eine angestoßene Foto-Animation (Veo/fal/M3) ist fertig (dauert Minuten → Push ideal).
3. **Neue Gesichts-Vorschläge** — z. B. nach Import: „X neue Vorschläge zum Bestätigen".
4. **Import/Scan abgeschlossen** — „N neue Fotos verarbeitet".
5. **Erinnerung** — „Heute vor X Jahren" (1×/Tag, opt-in).
6. (später) **Geteiltes Album geöffnet** — jemand hat deinen Share angesehen.

Alle **opt-in pro Typ** (Setting), kein Spam.

### Kanäle (zwei Welten)
- **Web (PWA):** **Web Push** via Service-Worker + **VAPID**-Schlüssel. Browser/OS-Benachrichtigung auch wenn der Tab zu ist. Funktioniert auf Desktop + Android-Chrome; iOS-Safari nur als installierte PWA (ab iOS 16.4).
- **iOS-App (SwiftUI):** **APNs** (Apple Push Notification service). Braucht ein Apple-Developer-Push-Zertifikat/Key + Geräte-Token-Registrierung. Der native Client registriert sein Device-Token beim Server.

### Architektur (auf vorhandenem aufbauen)
```
Ereignis (Task fertig / Beat)  →  notify(user_id, type, title, body, link)
                                      │
   push_subscriptions (DB)  ◄─────────┤  (pro User: web-push-sub ODER apns-token)
                                      ▼
        Web Push (pywebpush + VAPID)   |   APNs (httpx HTTP/2 + JWT, key p8)
```
- **Neue Tabelle** `push_subscriptions`: `user_id`, `kind` (web|apns), `endpoint/token`, `keys` (web), `created_at`. Migration via `_COLUMN_MIGRATIONS`/eigene Tabelle.
- **Service** `app/services/push.py`: `subscribe()`, `send(user_id, payload)`, pro Kanal ein Sender. Fehlertolerant (abgelaufene Subs entfernen).
- **Auslöser:** dort, wo Tasks fertig werden (z. B. `animate_photo_task`→done, `render_highlight_task`→done, `generate_weekly_highlight`, suggest_faces). Ein `notify(...)`-Aufruf am Ende.
- **Settings:** `push.enabled`, VAPID-Public/Private-Key, APNs-Key/Team/Bundle; pro User Opt-in-Flags je Typ.
- **Frontend Web:** Service-Worker (`/sw.js`) + „Benachrichtigungen aktivieren"-Button (Permission → Subscription → an Server). **iOS:** `UNUserNotificationCenter`-Permission + Token-Registrierung im `APIClient`.

### Empfehlung / Reihenfolge
1. **Web Push zuerst** (VAPID, kein Apple-Account nötig, deckt Desktop+Android+installierte PWA) — größter Hebel, kleinster Aufwand.
2. **APNs danach** (zusammen mit dem iOS-Release, braucht Apple-Dev-Setup).
3. Start mit **2 Typen**: „KI-Szene fertig" + „Highlight der Woche" (beide ohnehin asynchron → Push macht sie erst nützlich).

### Offene Punkte (Entscheidungen)
- Apple-Developer-Account/Push-Key vorhanden? (für APNs nötig)
- PWA-Installierbarkeit (manifest + SW) — gibt es ein Web-App-Manifest bereits?

---

## Teil B — Release-Readiness-Audit

Checkliste vor „echtem" Release / breiterer Nutzung. ✅ = heute erfüllt, ⚠️ = offen.

### Sicherheit
- ✅ Auth mit Access/Refresh-Token; `current_user`-Guards; Remote-Worker eigener Token.
- ⚠️ **Secrets in der DB-`settings`** (Gemini/fal/MapTiler-Keys, Remote-Token) — im Klartext. Prüfen: DB-Zugriff/Backups absichern; ggf. Verschlüsselung at-rest.
- ⚠️ **Rate-Limiting / Brute-Force** am Login? (prüfen)
- ⚠️ Share-Links: Ablauf/Passwort vorhanden — Default-Sicherheit prüfen.
- ⚠️ CORS/Origin, HTTPS-Erzwingung hinter nginx prüfen.

### Zuverlässigkeit (vieles diese Kampagne gehärtet)
- ✅ Atomare Transcodes (`.part`→`os.replace`), validiert (ffprobe).
- ✅ Clustering- & Highlight-Render-Verbindungs-Bug gefixt (`asyncio.to_thread`).
- ✅ Highlight-Reaper (hängende Jobs heilen sich).
- ✅ Zeitstempel app-weit korrekt (aware UTC).
- ✅ `.3gp`-Transcode-Bug gefixt.
- ⚠️ **Describe-Rückstau** (~76k) + **CPU-Queue** (~73k) — drainen langsam; ok, aber Monitoring.
- ⚠️ Error-Handling/Retry der Cloud-KI (Gemini/fal-Ausfälle) — `retry_failed_ai` vorhanden; Abdeckung prüfen.

### Performance / Skalierung
- ✅ Server-seitiges Map-Clustering, gechunktes Clustering (kein OOM).
- ⚠️ Queue-Trennung: `video`-Queue von Transcodes geflutet — ggf. dedizierte Queue/Worker für Highlights.
- ⚠️ Thumbnails/Embeddings-Backlog-Drain überwachen.

### Daten / Backup
- ✅ Originale unangetastet; Caches regenerierbar.
- ⚠️ **DB-Backup-Strategie** verifizieren (pg_dump-Cron? Zweitbox?). Restore mal testen.
- ℹ️ Alt-Zeitstempel um TZ-Offset verschoben (DST-variabel) — bewusst NICHT migriert (s. Bericht).

### Beobachtbarkeit
- ✅ Leitstand + `feature_logs` (Datei-Logs pro Kategorie).
- ⚠️ Zentrale Fehler-Alarmierung (z. B. Push/Mail bei `ERROR`-Spike)?

### iOS-Release
- ⚠️ Signing/Provisioning, App-Store/TestFlight-Pfad, Datenschutz-Texte (Fotos→Cloud-KI), Push-Entitlement.
- ✅ App baut (`xcodebuild` BUILD SUCCEEDED).

### Go-Live-Reihenfolge (Vorschlag)
1. Secrets/Backup absichern + Restore testen.
2. Web Push (Stufe 1).
3. Monitoring/Alarm bei ERROR-Spikes.
4. iOS: APNs + TestFlight + Store-Vorbereitung.
