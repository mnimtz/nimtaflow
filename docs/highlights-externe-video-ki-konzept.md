# Konzept: Externe Video-KI für Highlights

> Status: **Konzept / Entscheidungsvorlage** (kein Code). Roadmap-Punkt #5.
> Erstellt 2026-06-22. Preise mit „Stand Juni 2026" sind Momentaufnahmen — vor Bau verifizieren.
> Entscheidung des Users: **erst dieses Dokument, dann bauen.**

## 1. Ausgangslage (was es heute schon gibt)

PhotoFlow hat bereits ein **lokales** Highlights-System — komplett ohne externe KI:

- **Model** `Highlight` (`backend/app/models/highlight.py`): `status` (pending/rendering/done/error),
  `motto`, `params` (JSON), `file_path`, `duration_sec`, `photo_count`, `cover_photo_id`.
- **Service** `backend/app/services/highlights.py`:
  - `select_photos_for_motto()` — wählt Fotos pro „Motto" (Person über Jahre, schönste Lächeln,
    Mutter/Vater & Kind, Muttertag/Vatertag, Jahresrückblick, Reise, Saison …).
  - `render_slideshow()` — baut aus den **gecachten `thumb_large`-JPEGs** per **ffmpeg** eine MP4
    (xfade-Crossfades, Concat-Fallback). Hard-fail-sicher: es entsteht immer eine Datei.

Das ist ein **Slideshow-Generator**: echte Fotos, Überblendungen, Musik optional. Schnell, gratis,
läuft lokal. Was es **nicht** kann: Standbilder *bewegen* (Parallax/Animation), KI-Schnitt,
Sprecher/Voiceover, generierte Übergänge, „cineastische" Clips.

**Vorhandene KI-Infrastruktur, auf der wir aufsetzen können:**
- Provider-Abstraktion in den Settings: `ai.provider`, `ai.gemini.*`, `ai.openai.*`,
  `ai.anthropic.*`, `ai.ollama.*`, `ai.local.model`; für Video separat `video.ai_provider`,
  `video.local.model`. Services unter `backend/app/services/ai/`.
- **Worker-Queues** (Celery): u. a. `video`, GPU-Worker `worker-1`, plus **Remote-Compute**
  (Zweitbox/Mac-Worker) über `/api/remote/*` mit `X-Remote-Token`.
- Asynchrones Job-Muster ist schon etabliert (Highlight.status, Transcode-Tasks).

## 2. Ziel & Anwendungsfälle

„Externe Video-KI" heißt: zusätzlich zur Slideshow **echte Video-Generierung** zukaufen, wo sie
einen Mehrwert bringt. Sinnvolle Anwendungsfälle für eine Foto-Verwaltung:

1. **Standbild → Clip („Foto zum Leben erwecken")** — *image-to-video*. Ein Lieblingsfoto wird zu
   3–8 s sanfter Bewegung (Kamerafahrt, Parallax, leichte Mimik). Der mit Abstand realistischste &
   günstigste Anwendungsfall (Referenzbild führt das Modell → weniger Halluzination).
2. **„Highlight der Woche"** — automatisch wöchentlich: beste Fotos der Woche/eines Events → ein
   kurzer, hübsch geschnittener Clip. Kombi aus Slideshow + ein paar animierten Schlüsselbildern.
3. **Motto-Highlights aufwerten** — die bestehenden Mottos (Person über Jahre etc.) optional als
   „Premium"-Variante mit animierten Übergängen / Intro statt nur Crossfade.
4. **(später) Voiceover/Untertitel** — KI-Erzähltext zum Rückblick (TTS), getrennt vom Bildmodell.

Wichtig: **text-to-video** (Szene aus dem Nichts) ist für eine *Foto*-App kaum sinnvoll — wir wollen
die echten Erinnerungen, nicht erfundene. Fokus daher klar auf **image-to-video** der echten Fotos.

## 3. Provider-Vergleich (Stand Juni 2026)

Alle genannten können **image-to-video** (für unseren Hauptanwendungsfall entscheidend). Preise sind
Output-basiert (pro Sekunde erzeugtes Video), grob gerundet, ohne Steuern, Listenpreise.

| Provider / Modell | image→video | Audio | API | Preis (≈) | 8-s-Clip (≈) | Anmerkung |
|---|---|---|---|---|---|---|
| **Google Veo 3.1 Fast** | ✅ | ✅ | Gemini/Vertex | **$0.15/s** | ~$1.20 | Bestes Preis/Leistung mit Ton; passt zu vorhandener Gemini-Anbindung |
| **Google Veo 3.1 Standard** | ✅ | ✅ | Gemini/Vertex | $0.40/s | ~$3.20 | Höchste Qualität, teuer |
| **OpenAI Sora 2 Standard** | ✅ | ✅ | OpenAI | **$0.10/s** (720p) | ~$0.80 | Günstig — **aber API-Sunset 24.09.2026** ⚠️ |
| **OpenAI Sora 2 Pro** | ✅ | ✅ | OpenAI | $0.30–0.70/s | ~$2.40+ | Batch ~halber Preis; selbe Sunset-Warnung |
| **Runway Gen-4 Turbo** | ✅ | – | Runway | **$0.05/s** (5 cr.) | ~$0.40 | Günstigster „Profi"-API-Tarif; Credits $0.01 |
| **Runway Gen-4 (Std/4.5)** | ✅ | – | Runway | $0.25/s (25 cr.) | ~$2.00 | Höhere Qualität |
| **Kling AI** | ✅ | tlw. | (inoffiz./Abo) | Abo ab ~$6–10/mo | — | Günstigster Einstieg, aber API-Lage uneinheitlich |
| **Luma Dream Machine (Ray)** | ✅ | – | Luma | ~$0.32/Generierung | ~$0.32 | Einfache Pauschale pro Clip; gute Foto-Treue |

**Kurzbewertung für PhotoFlow:**
- **Veo 3.1 Fast** — strategisch am besten: Gemini ist **schon angebunden** (`ai.gemini.api_key`),
  ein Schlüssel/Provider weniger, Ton inklusive, solide Foto-Animation, kein Sunset-Risiko.
- **Runway Gen-4 Turbo** — günstigste seriöse API ($0.05/s), aber zweiter Anbieter/Key nötig, kein Ton.
- **Sora 2 Standard** — billig und gut, aber **API endet 24.09.2026** → für ein dauerhaftes Feature
  riskant, nur als Option führen, nicht als Default.
- **Luma** — einfachstes Abrechnungsmodell (pro Clip), gute Wahl als Zweit-Provider.
- **Kling** — günstig für manuelle Nutzung, API-Anbindung derzeit zu wackelig für Produktion.

## 4. Kosten-Realität

Der Hebel ist **Anzahl & Länge der animierten Clips**, nicht das Modell allein. Beispielrechnung
mit **Veo 3.1 Fast ($0.15/s)** und **Runway Gen-4 Turbo ($0.05/s)**:

| Szenario | Animierte Clips | Sekunden gesamt | Veo Fast | Runway Turbo |
|---|---|---|---|---|
| 1 Foto „zum Leben erwecken" (5 s) | 1 | 5 | ~$0.75 | ~$0.25 |
| „Highlight der Woche" (5 Schlüsselbilder × 4 s, Rest Slideshow) | 5 | 20 | ~$3.00 | ~$1.00 |
| Motto-Premium (8 animierte Übergänge × 3 s) | 8 | 24 | ~$3.60 | ~$1.20 |
| Wöchentlich automatisch, 1 Jahr (52 × 20 s) | — | ~1040 | ~$156/Jahr | ~$52/Jahr |

**Konsequenzen fürs Design:**
- **Hybrid statt Voll-KI:** Slideshow (gratis, ffmpeg) bleibt das Rückgrat; KI animiert nur
  **wenige Schlüsselbilder**. So bleiben die Kosten zweistellig pro Jahr statt dreistellig.
- **Harte Kostenbremse nötig:** monatliches Budget/Limit in Sekunden + Clips, sonst Kostenrisiko.
- **Aggressiv cachen:** jeder generierte Clip wird dauerhaft gespeichert (`/cache/highlights/…`),
  nie zweimal für dasselbe Foto+Parameter erzeugen.
- **Opt-in & manuell zuerst:** kein automatisches Geld-Ausgeben ohne explizite Nutzeraktion;
  „Highlight der Woche" automatisch erst, wenn der User es bewusst aktiviert.

## 5. Architektur-Vorschlag

Konsequent auf vorhandenen Mustern aufbauen — minimale neue Konzepte.

```
Nutzer wählt Motto / „Foto animieren" / „Highlight der Woche"
        │
        ▼
POST /highlights (params, use_ai: bool, ai_clips: int)   ── erzeugt Highlight(status=pending)
        │  .delay()  (Celery, Queue „video")
        ▼
render_highlight_task
  1. select_photos_for_motto()                         (bestehend)
  2. WENN use_ai:  Schlüsselbilder wählen (Top-N nach Qualität/Gesicht/Score)
        └─ pro Bild: VideoAIProvider.animate(image, prompt, seconds)
              ├─ Provider laut `highlights.ai_provider` (veo|runway|luma|sora|none)
              ├─ Aufruf via services/ai/video_gen/<provider>.py  (neue, dünne Adapter)
              ├─ Budget-Check VOR jedem Call (Sekunden-Zähler im Monat)
              └─ Ergebnis-Clip → /cache/highlights/clips/{hash}.mp4   (idempotent)
  3. ffmpeg: Slideshow + animierte Clips + (optional) Musik/Voiceover  → finale MP4
  4. Highlight.status = done, file_path, duration_sec, photo_count
```

- **Neuer Service-Layer** `backend/app/services/ai/video_gen/` mit einem schmalen Interface
  `animate(image_path, prompt, seconds, **opts) -> mp4_path` und je einem Adapter pro Provider.
  Spiegelt die bestehende `ai.provider`-Abstraktion (Describe/Chat).
- **Queue:** läuft auf der `video`-Queue; lange Wartezeiten (Provider brauchen 30 s–mehrere Min)
  → **Polling/Webhook** im Task, `status=rendering` währenddessen. Kein API-Thread blockiert.
- **Remote-fähig:** Generierung kann auch über die vorhandene `/api/remote/*`-Schiene laufen
  (z. B. Mac-Worker hält den Provider-Key), falls Keys nicht auf der Prod-Box liegen sollen.
- **Idempotenz/Cache:** Clip-Dateiname = Hash aus (photo_id, provider, prompt, seconds, version).
  Re-Render eines Highlights nutzt vorhandene Clips → keine Doppelkosten.
- **Migrationen:** `_COLUMN_MIGRATIONS` in `main.py` für neue Spalten (z. B.
  `highlights.ai_seconds_used`, `highlights.ai_provider`).

## 6. Einstellungen (neue Keys, konsistent zum bestehenden Schema)

| Key | Default | Zweck |
|---|---|---|
| `highlights.ai_enabled` | `false` | KI-Video global an/aus (Opt-in) |
| `highlights.ai_provider` | `veo` | `veo` \| `runway` \| `luma` \| `sora` \| `none` |
| `highlights.ai_clip_seconds` | `4` | Länge pro animiertem Clip |
| `highlights.ai_max_clips` | `5` | max. animierte Clips pro Highlight |
| `highlights.ai_budget_seconds_month` | `300` | **harte** Monatsbremse (Sekunden) |
| `highlights.weekly_enabled` | `false` | „Highlight der Woche" automatisch |
| `ai.veo.api_key` / nutzt `ai.gemini.api_key` | – | Veo läuft über Gemini-Key |
| `ai.runway.api_key`, `ai.luma.api_key` | – | nur falls jeweiliger Provider gewählt |
| `highlights.ai_prompt` | (Vorlage) | Steuer-Prompt für die Animation (Stil/Bewegung) |

Im UI (SettingsPage → Highlights): Provider-Auswahl, Budget-Anzeige („genutzt X/300 s diesen Monat"),
Schalter für Auto-Wochenhighlight, Hinweis auf Kosten.

## 7. Empfehlung

1. **Hybrid-Ansatz**, nicht Voll-KI: Slideshow bleibt Default & gratis; KI animiert nur wenige
   Schlüsselbilder. Hält Qualität hoch *und* Kosten klein.
2. **Erst-Provider: Google Veo 3.1 Fast** — nutzt den vorhandenen Gemini-Key, Ton inklusive,
   kein Sunset-Risiko, gutes Preis/Leistung. **Zweit-Provider optional: Luma** (einfachste
   Abrechnung) oder **Runway Gen-4 Turbo** (billigster Sekundenpreis).
3. **Sora 2 nur als Option führen**, nicht als Default (API-Sunset 24.09.2026).
4. **Harte Budget-Bremse + Cache + Opt-in** sind nicht verhandelbar (Kostenrisiko).
5. **MVP zuerst:** ein einziger Anwendungsfall — **„Foto animieren"** (1 Bild → 1 Clip, manuell
   ausgelöst) — über Veo. Das validiert Anbindung, Qualität, Kosten end-to-end, bevor wir
   „Highlight der Woche" und Auto-Generierung bauen.

## 8. Risiken & offene Fragen

- **Kosten laufen weg**, wenn Auto-Generierung zu früh aktiviert wird → Budget-Bremse Pflicht.
- **Datenschutz:** echte Familienfotos gehen an einen externen Cloud-Anbieter. Muss dem User klar
  kommuniziert werden (Consent pro Provider). Lokale Slideshow bleibt die private Default-Option.
- **Latenz:** Generierung dauert; UI muss „in Arbeit" sauber zeigen (status=rendering, Polling).
- **Provider-Stabilität/Preisänderungen:** Adapter dünn halten, Provider austauschbar.
- **Qualität von image-to-video** schwankt (Gesichter können „verlaufen") → konservative Prompts,
  kurze Clips, Vorschau & Verwerfen-Option.

## 9. Nächste Schritte (wenn freigegeben)

1. MVP „Foto animieren" über **Veo 3.1 Fast**: Adapter `services/ai/video_gen/veo.py`, Settings
   `highlights.ai_enabled/ai_provider/ai_budget_seconds_month`, Button in der Foto-Lightbox,
   Job auf `video`-Queue, Clip-Cache, Budget-Zähler.
2. Test mit echten Fotos (Qualität/Kosten/Latenz messen) → Entscheidung Zweit-Provider.
3. „Highlight der Woche" + Auto-Modus (opt-in) auf dem MVP aufbauen.
4. iOS-Parität (Anzeige der KI-Highlights) im Rahmen von Roadmap #7.

---

## Nachtrag (Juni 2026): Günstigere, Gratis- & lokale Optionen

Auslöser: Frage nach billigeren Alternativen, Gratis-Kontingenten und „Google Omni".

### Gratis-API-Kontingent für Video? → praktisch **nein**
- **Veo (Gemini API)** hat **keinen** Free-Tier — Video ist paid-only.
- **„Gemini Omni"** = Googles **Consumer**-Videogenerierung (Flow/Whisk/Gemini-App), 50 Gratis-Credits/Tag (~2 Fast-Clips/Tag). **Nur UI, keine API** → **nicht in PhotoFlow integrierbar.**
- Einmalige **Test-Credits** gibt es bei Aggregatoren: **fal.ai ~$20 gratis** (Business-Mail), **Hailuo/MiniMax** ~200 Welcome-Credits + Daily (~4–6 kurze Clips, Wasserzeichen).

### Billigste Cloud (pro-Clip, via Aggregator fal.ai)
| Modell (über fal.ai) | Preis (≈) | Einordnung |
|---|---|---|
| **Vidu** | ~$0.0375/s | günstigster Sekundenpreis |
| **MiniMax Hailuo 02** | ~$0.28/Clip (~$0.046/s) | bestes Preis/Leistung „billig" |
| **Stable Video Diffusion** | ~$0.20 / 4 s | günstig, einfache Bewegung |
| **Veo 3 / Sora 2 (über fal)** | ~$0.50 / 5 s (= $0.10/s) | **billiger als Veo direkt** ($0.15/s)! |
- **fal.ai ist attraktiv:** ein Key → viele Modelle (Hailuo billig … Veo/Sora Premium), $20 gratis zum **echten Testen** (löst genau das Problem, dass Veo direkt nicht gratis testbar ist).

### Lokal & gratis (self-hosted) — passt zu eurem Setup
- **Prod-Box hat KEINE CUDA-GPU** (nur Intel-iGPU/QSV) → dort läuft keine Video-Diffusion.
- **M3-Mac** (macht schon Qwen-Video via MLX) ist der einzige lokale Weg:
  - **LTX-2.3 via MLX**: läuft auf M3, **~5 Min/Clip**, **0 € pro Clip**, **Fotos bleiben lokal** (Privacy!). Es gibt sogar eine native macOS-App (`ltx-video-mac`). **Empfehlung für lokal.**
  - **Wan 2.2** auf Apple Silicon: praktisch zu langsam (~82 Min für 2 s auf M1 Max) → nicht praktikabel.

### Aktualisierte Empfehlung
1. **Zum Testen JETZT: fal.ai** ($20 gratis) — Provider `fal` in `video_gen/` einbauen, damit überhaupt **kostenlos** evaluierbar (Veo direkt war ja nicht gratis testbar). Modellwahl pro Setting (Hailuo billig / Veo premium).
2. **Für Dauerbetrieb gratis + privat: LTX-2.3 lokal auf dem M3** — neuer M3-Worker analog `com.photoflow.m3video`, Provider `local`. Kein laufender Cent, Familienfotos verlassen den Server nicht; Tradeoff: ~5 Min/Clip, Qualität < Veo.
3. **Veo direkt** bleibt die Premium-Option (beste Qualität+Ton), aber teurer und nicht gratis testbar.
- Architektur trägt das schon: `video_gen/`-Adapterschicht → Provider `veo` (gebaut), `fal`, `local` ergänzbar; Setting `highlights.ai_provider`.

### Quellen Nachtrag (Stand Juni 2026)
- Gemini API Free-Tier / Veo paid-only: https://ai.google.dev/gemini-api/docs/pricing
- Gemini Omni (Consumer-Video): https://gemini.google/overview/video-generation/
- fal.ai Preise & Free Credits: https://fal.ai/pricing · https://www.getaiperks.com/en/ai/fal-ai-free-credits-2026
- Hailuo/MiniMax Free + Preise: https://costbench.com/software/ai-video-generators/hailuo-ai/
- Open-Source lokal (LTX/Wan/CogVideoX): https://ltx.io/blog/best-open-source-video-generation-models · https://www.hyperstack.cloud/blog/case-study/best-open-source-video-generation-models
- LTX auf Apple Silicon (~5 Min/Clip, MLX): https://lilting.ch/en/articles/ltx2-wan22-mac-local-video-gen · https://github.com/james-see/ltx-video-mac

---

### Quellen (Preise, Stand Juni 2026)
- Veo 3 / 3.1 Pricing: https://www.veo3ai.io/blog/veo-3-api-pricing-2026 · https://costgoat.com/pricing/google-veo
- Runway API Pricing: https://docs.dev.runwayml.com/guides/pricing/ · https://academy.runwayml.com/models-pricing
- OpenAI Sora 2 Pricing (inkl. Sunset 24.09.2026): https://costgoat.com/pricing/sora · https://openai.com/api/pricing/
- Luma Dream Machine Pricing: https://lumalabs.ai/pricing · https://www.eesel.ai/blog/luma-ai-pricing
- Kling AI Pricing: https://kling.ai/app/membership/membership-plan · https://www.eesel.ai/blog/kling-ai-pricing
