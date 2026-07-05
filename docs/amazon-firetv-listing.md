# Amazon Appstore — FireTV Listing (NimtaFlow)

> Zum Reinkopieren in die Amazon Developer Console.
> Zeichenlimits: Titel ≤250, Kurzbeschreibung ≤1200, Lange Beschreibung ≤4000.
> Wichtig: Amazon indexiert Keywords direkt aus dem Beschreibungstext — keine
> separate Keywords-Tabelle. Relevante Begriffe daher bewusst in den Text einarbeiten.

---

## App-Titel
`NimtaFlow – Foto & Video für FireTV`

---

## Kurzbeschreibung (≤1200 Zeichen)

**DE:**
```
Verbinde deinen Amazon Fire TV mit deiner eigenen Foto- und Videobibliothek.
NimtaFlow zeigt deine Fotos & Videos direkt vom eigenen Server auf dem großen
Bildschirm – Galerie, Alben, Personen, Erinnerungs-Slideshow und automatischer
Bildschirmschoner. Self-hosted, privat, ohne Abo.
```

**EN:**
```
Connect your Amazon Fire TV to your own photo and video library.
NimtaFlow displays your photos & videos directly from your own server on the big
screen – gallery, albums, people, memories slideshow and automatic screensaver.
Self-hosted, private, no subscription.
```

---

## Lange Beschreibung (≤4000 Zeichen)

**DE:**
```
Deine Fotos. Dein Server. Dein Fernseher.

NimtaFlow für Fire TV verbindet deinen Amazon Fire TV Stick oder Fire TV Cube mit
deiner selbst gehosteten NimtaFlow-Fotoverwaltung. Keine Cloud-Pflicht, kein Abo –
deine Bilder und Videos bleiben auf deinem eigenen Server und werden einfach auf dem
großen Wohnzimmerbildschirm angezeigt.

WICHTIG: Diese App ist der Fire-TV-Client für einen laufenden NimtaFlow-Server
(selbst gehostet auf Heimserver, NAS oder Mini-PC). Beim ersten Start scannst du
einfach einen QR-Code im Web-Interface – fertig.

WAS DICH ERWARTET

• Galerie — alle Fotos & Videos in einer übersichtlichen Grid-Ansicht, komfortabel
  per Fernbedienung oder D-Pad navigierbar.

• Alben — greife auf deine manuellen und Smart-Alben zu und blättere durch die
  enthaltenen Bilder und Videos.

• Personen — deine erkannten Personen und deren Fotos auf dem Sofa browsen.

• Erinnerungen — „Heute vor X Jahren": automatische Rückblicke auf vergangene
  Momente aus deiner Bibliothek.

• Slideshow — starte eine zufällig gemischte Diashow aus deiner gesamten Sammlung
  oder aus einzelnen Alben, mit einstellbarem Tempo.

• Bildschirmschoner / Daydream — NimtaFlow aktiviert sich als automatischer
  Bildschirmschoner deines Fire TV. Zeigt deine eigenen Fotos statt generischer
  Stockbilder. Konfigurierbar: alle Fotos, bestimmte Personen, Alben oder Highlights.
  Mit optionaler Ort- und Datumsanzeige.

• Video-Wiedergabe — spielt deine Videos im eingebauten Player mit ExoPlayer ab,
  inklusive Untertitel-Support.

• Favoriten — markiere Lieblingsfotos direkt per Fernbedienungstaste.

SICHER VERBINDEN
Der Login erfolgt per QR-Code-Scan aus dem Browser – kein Tippen von Passwörtern
auf der Fernbedienung. Token werden sicher lokal gespeichert.

KEIN KONTO BEI UNS NÖTIG
NimtaFlow als Dienst existiert nicht – du betreibst deinen eigenen Server.
Deine Daten verlassen nie dein Heimnetz (außer du öffnest ihn selbst).

Selbsthosting, Datenschutz, große Bildschirme – NimtaFlow für Fire TV.
```

**EN:**
```
Your photos. Your server. Your TV.

NimtaFlow for Fire TV connects your Amazon Fire TV Stick or Fire TV Cube to your
self-hosted NimtaFlow photo library. No cloud subscription required – your photos
and videos stay on your own server and are simply displayed on the big living room
screen.

IMPORTANT: This app is the Fire TV client for a running NimtaFlow server (self-hosted
on a home server, NAS or mini-PC). On first launch, simply scan a QR code from the
web interface – that's it.

WHAT TO EXPECT

• Gallery — all photos & videos in a clear grid view, comfortably navigable with
  remote or D-pad.

• Albums — access your manual and smart albums and browse their photos and videos.

• People — browse recognised people and their photos from the couch.

• Memories — "Today X years ago": automatic flashbacks to past moments from your
  library.

• Slideshow — start a randomly shuffled slideshow from your entire collection or
  specific albums, with adjustable speed.

• Screensaver / Daydream — NimtaFlow activates as an automatic Fire TV screensaver.
  Shows your own photos instead of generic stock images. Configurable: all photos,
  specific people, albums or highlights. With optional location and date overlay.

• Video playback — plays your videos in the built-in ExoPlayer-powered player,
  including subtitle support.

• Favourites — mark favourite photos directly with a remote button.

SECURE CONNECTION
Login via QR code scan from the browser – no typing passwords on the remote control.
Tokens are stored securely on device.

NO ACCOUNT WITH US NEEDED
NimtaFlow as a service does not exist – you run your own server.
Your data never leaves your home network (unless you open it yourself).

Self-hosting, privacy, big screens – NimtaFlow for Fire TV.
```

---

## Kategorie
**Primär:** Entertainment  
**Sekundär:** Photo & Video

## Inhalts-Rating
→ Im Developer Console Fragebogen: keine Gewalt, keine Sex-Inhalte, keine In-App-Käufe.
→ Erwartetes Rating: **Everyone (Alle)**

---

## Screenshots (Pflicht: mindestens 3)
Format: **1920 × 1080 px** (JPG oder PNG, max. 5 MB)

Empfohlene Szenen:
1. Galerie-Grid mit Fotos und Videos
2. Album-Übersicht
3. Personen-Ansicht
4. Slideshow / Bildschirmschoner aktiv
5. Video-Player mit Steuerung

> Tipp: Über den Fire TV Simulator (Android Studio AVD, TV-Profil 1920×1080)
> oder direkt mit `adb shell screencap -p /sdcard/screen.png` + `adb pull`.

---

## APK-Anforderungen für Amazon Appstore

Amazon akzeptiert **keinen Debug-APK** — es wird ein signierter Release-Build benötigt.

### Schritt 1: Keystore erstellen (einmalig)
```bash
keytool -genkey -v -keystore nimtaflow-firetv.jks \
  -alias nimtaflow-firetv \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=NimtaFlow FireTV, OU=NimtaFlow, O=Nimtz, L=DE, ST=DE, C=DE"
```
→ Keystore + Passwörter sicher verwahren (nie ins Repo!)

### Schritt 2: Signing-Secrets in GitHub hinterlegen
| Secret | Inhalt |
|--------|--------|
| `FIRETV_KEYSTORE_BASE64` | `base64 -i nimtaflow-firetv.jks` |
| `FIRETV_KEY_ALIAS` | `nimtaflow-firetv` |
| `FIRETV_KEY_PASSWORD` | dein Key-Passwort |
| `FIRETV_STORE_PASSWORD` | dein Store-Passwort |

### Schritt 3: CI baut signierten Release-APK
→ Workflow bereits vorbereitet (`.github/workflows/firetv-build.yml`)

---

## Submission-Checkliste Amazon Developer Console
- [ ] Amazon Developer Account vorhanden (developer.amazon.com)
- [ ] Neue App anlegen → Typ: Android
- [ ] Plattform: Fire TV auswählen
- [ ] APK hochladen (Release, signiert)
- [ ] Listing DE + EN ausgefüllt
- [ ] Screenshots hochgeladen (min. 3 × 1920×1080)
- [ ] App-Icon: 512×512 px (PNG, kein Alpha)
- [ ] Content Rating Fragebogen ausgefüllt
- [ ] Einreichung absenden → Review ~1-3 Werktage

---

## Suchbegriffe (in Beschreibung integriert — Amazon indexiert Text)
`Foto`, `Fotos`, `Galerie`, `Bildschirmschoner`, `Screensaver`, `Slideshow`,
`Diashow`, `Video`, `Alben`, `Personen`, `Erinnerungen`, `self-hosted`,
`selbst gehostet`, `private cloud`, `Fotoarchiv`, `Fotoviewer`, `NAS`, `Heimserver`
