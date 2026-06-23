# Drittanbieter-Lizenzen & Hinweise · Third-party licenses & notices

> **Deutsch zuerst, English below.**
> NimtaFlow selbst steht unter **AGPL-3.0**. Es bündelt **keine** KI-Modell-Gewichte —
> diese werden zur Laufzeit von den jeweiligen Anbietern geladen und unterliegen deren
> Lizenz. Dieses Dokument listet die eingebundenen Komponenten und ihre Lizenzen/Attributionen.

---

## ⚠️ Wichtiger Hinweis zu den KI-Modellen (Disclaimer)

Die **Standard-Modelle** werden **zur Laufzeit von den Anbietern heruntergeladen** (nicht im
Repository enthalten) und sind teils **nur für nicht-kommerzielle Nutzung** lizenziert:

| Modell | Zweck | Lizenz | Kommerziell? |
|---|---|---|---|
| **InsightFace `buffalo_l`** (SCRFD + ArcFace) | Gesichtserkennung | nur **nicht-kommerziell / Forschung** | ❌ |
| **`jinaai/jina-clip-v2`** | Bild/Text-Embeddings (Suche) | **CC-BY-NC 4.0** (nicht-kommerziell) | ❌ |
| `microsoft/Florence-2-base` | Bildbeschreibung (lokal) | MIT | ✅ |
| `Qwen2.5-VL` / `Qwen3-VL` (MLX) | Bild/Video-Beschreibung (lokal) | Apache-2.0 | ✅ |
| `Helsinki-NLP/opus-mt-en-de` | Übersetzung | CC-BY-4.0 (Attribution) | ✅ (mit Nennung) |
| facenet-pytorch (Alternativ-Engine) | Gesichtserkennung | Code MIT; Gewichte VGGFace2 = Forschung | ⚠️ |

**Du als Betreiber** bist für eine **lizenzkonforme Nutzung** der geladenen Modelle verantwortlich.
Für **rein privates / nicht-kommerzielles Self-Hosting** sind die Standard-Modelle in Ordnung.
Für **kommerzielle** Nutzung bitte auf permissiv lizenzierte Engines wechseln (z. B.
**YuNet/SFace** für Gesichter, **OpenCLIP** bzw. **jina-clip-v1 (Apache-2.0)** für Embeddings).

*(Diese Aufstellung ist eine Einschätzung, keine Rechtsberatung — Lizenzen können sich ändern.)*

## Karten / Map-Tiles (Attributionspflicht)
- **OpenStreetMap** © OpenStreetMap contributors (ODbL)
- **CARTO** Basemaps (© CARTO, © OpenStreetMap contributors)
- **Esri** World Imagery (© Esri, Maxar, Earthstar Geographics)
- **OpenTopoMap** (CC-BY-SA, © OpenTopoMap / SRTM)
- **MapTiler** (Key des Betreibers; © MapTiler © OpenStreetMap contributors)

## KI-Dienste (Cloud, „Bring your own key")
Google Gemini/Veo, OpenAI, fal.ai — werden nur mit dem **eigenen API-Schlüssel des Betreibers**
genutzt; es gelten die ToS des jeweiligen Anbieters. Nutzung optional, standardmäßig aus.

## Weitere Komponenten (permissiv)
Frontend: React, Vite, TailwindCSS, @tanstack/react-query, axios, zustand, clsx (MIT) ·
Leaflet (BSD-2) · MapLibre GL (BSD-3) · lucide-react (ISC) · yet-another-react-lightbox (MIT) ·
Inter-Schrift (SIL OFL). Backend: FastAPI, SQLAlchemy, Celery u. a. (MIT/BSD/Apache).

---

# English

NimtaFlow is licensed under **AGPL-3.0** and bundles **no** AI model weights — they are
downloaded at runtime from their providers and remain under their respective licenses.

**AI model disclaimer:** the **default models are downloaded at runtime** (not shipped in this
repo) and some are licensed **for non-commercial use only** — notably **InsightFace `buffalo_l`**
(non-commercial/research) and **`jina-clip-v2`** (CC-BY-NC 4.0). **You, the operator, are
responsible for license-compliant use.** Personal / non-commercial self-hosting is fine; for
**commercial** use switch to permissive engines (e.g. **YuNet/SFace** for faces, **OpenCLIP** or
**jina-clip-v1 (Apache-2.0)** for embeddings). *This is guidance, not legal advice.*

Map tiles require attribution (OpenStreetMap contributors, CARTO, Esri, OpenTopoMap, MapTiler).
Cloud AI (Gemini/Veo/OpenAI/fal.ai) is opt-in and used only with the operator's own API key,
under each provider's ToS.
