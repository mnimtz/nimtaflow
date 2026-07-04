#!/usr/bin/env bash
# NimtaFlow FireTV — APK bauen und auf den Server laden
# Aufruf: ./build-and-deploy.sh
# Einmalige Vorbereitung: brew install gradle && brew install --cask android-commandlinetools
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROXMOX_HOST="root@192.168.1.44"
LXC_ID=101
APK_SRC="$SCRIPT_DIR/app/build/outputs/apk/debug/app-debug.apk"

# ── Android SDK ────────────────────────────────────────────────────────────────
# Suche Android SDK an den üblichen Homebrew-Orten
if [[ -d "$HOME/Library/Android/sdk" ]]; then
    export ANDROID_HOME="$HOME/Library/Android/sdk"
elif [[ -d "/opt/homebrew/share/android-commandlinetools" ]]; then
    export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"
elif [[ -d "/usr/local/share/android-commandlinetools" ]]; then
    export ANDROID_HOME="/usr/local/share/android-commandlinetools"
else
    echo "❌ Android SDK nicht gefunden."
    echo ""
    echo "Einmalig installieren:"
    echo "  brew install gradle"
    echo "  brew install --cask android-commandlinetools"
    echo "  sdkmanager 'platforms;android-35' 'build-tools;35.0.0'"
    echo "  yes | sdkmanager --licenses"
    exit 1
fi

# ── Gradle prüfen ─────────────────────────────────────────────────────────────
if ! command -v gradle &>/dev/null; then
    echo "❌ Gradle nicht gefunden. Installieren mit: brew install gradle"
    exit 1
fi

echo "✦ NimtaFlow FireTV — Build startet..."
echo "  Android SDK: $ANDROID_HOME"
echo "  Gradle:      $(gradle --version | head -1)"
echo ""

# ── APK bauen ─────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
gradle assembleDebug

if [[ ! -f "$APK_SRC" ]]; then
    echo "❌ APK nicht gefunden nach Build — Gradle-Fehler?"
    exit 1
fi

APK_SIZE=$(du -sh "$APK_SRC" | cut -f1)
echo ""
echo "✓ APK gebaut: $APK_SIZE"

# ── Auf Server laden ──────────────────────────────────────────────────────────
echo "↑ Auf Server laden..."
scp -q "$APK_SRC" "$PROXMOX_HOST:/tmp/nimtaflow-tv.apk"
ssh -q "$PROXMOX_HOST" "pct push $LXC_ID /tmp/nimtaflow-tv.apk /firetv.apk && rm /tmp/nimtaflow-tv.apk"

echo ""
echo "✓ Fertig! APK verfügbar unter:"
echo "  http://192.168.0.193:8090/firetv.apk"
echo ""
echo "Auf dem FireTV: Downloader-App öffnen → URL eingeben → Installieren"
