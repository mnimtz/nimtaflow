#!/usr/bin/env bash
# NimtaFlow FireTV — APK bauen und auf den Server laden
# Aufruf: ./build-and-deploy.sh
# Einmalige Vorbereitung: brew install gradle && brew install --cask android-commandlinetools
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROXMOX_HOST="root@192.168.1.44"
LXC_ID=101
APK_SRC="$SCRIPT_DIR/app/build/outputs/apk/debug/app-debug.apk"

# ── Java finden und JAVA_HOME setzen ──────────────────────────────────────────
# (sdkmanager braucht JAVA_HOME, auch wenn Gradle Java selbst findet)
if [[ -z "$JAVA_HOME" ]]; then
    JAVA_HOME="$(/usr/libexec/java_home 2>/dev/null)" || true
fi
if [[ -z "$JAVA_HOME" ]]; then
    for v in 21 17 11; do
        for prefix in /opt/homebrew /usr/local; do
            if [[ -d "$prefix/opt/openjdk@$v" ]]; then
                JAVA_HOME="$prefix/opt/openjdk@$v"; break 2
            fi
        done
    done
fi
if [[ -z "$JAVA_HOME" ]]; then
    echo "❌ Java nicht gefunden. Installieren mit: brew install openjdk@17"
    exit 1
fi
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

# ── Android SDK ────────────────────────────────────────────────────────────────
if [[ -d "$HOME/Library/Android/sdk" ]]; then
    export ANDROID_HOME="$HOME/Library/Android/sdk"
elif [[ -d "/opt/homebrew/share/android-commandlinetools" ]]; then
    export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"
elif [[ -d "/usr/local/share/android-commandlinetools" ]]; then
    export ANDROID_HOME="/usr/local/share/android-commandlinetools"
else
    echo "❌ Android SDK nicht gefunden."
    echo "Einmalig installieren: brew install --cask android-commandlinetools"
    exit 1
fi

# ── Gradle prüfen ─────────────────────────────────────────────────────────────
if ! command -v gradle &>/dev/null; then
    echo "❌ Gradle nicht gefunden. Installieren mit: brew install gradle"
    exit 1
fi

echo "✦ NimtaFlow FireTV — Build startet..."
echo "  Java:        $JAVA_HOME"
echo "  Android SDK: $ANDROID_HOME"
echo "  Gradle:      $(gradle --version | head -1)"
echo ""

# ── SDK-Pakete und Lizenzen sicherstellen ─────────────────────────────────────
SDKMGR="$(find "$ANDROID_HOME" -name sdkmanager 2>/dev/null | head -1)"
if [[ -n "$SDKMGR" ]]; then
    # Lizenzen akzeptieren (sdkmanager schreibt korrekte Hashes selbst)
    yes 2>/dev/null | "$SDKMGR" --licenses >/dev/null 2>&1 || true
    # Pakete installieren falls noch nicht vorhanden
    "$SDKMGR" "platforms;android-35" "build-tools;35.0.0" 2>&1 \
        | grep -v "^$\|Parsing\|Warning: Failed\|^[[:space:]]*$" || true
else
    echo "⚠ sdkmanager nicht gefunden — Lizenzen manuell schreiben..."
    LICENSE_DIR="$ANDROID_HOME/licenses"
    mkdir -p "$LICENSE_DIR"
    printf "\n8933bad161af4178b1185d1a37fbf41ea5269c55\nd56f5187479451eabf01fb78af6dfcb131a6481e\n24333f8a63b6825ea9c5514f83c2829b004d1fee\n" \
        > "$LICENSE_DIR/android-sdk-license"
    printf "\n84831b9409646a918e30573bab4c9c91346d8abd\n" \
        > "$LICENSE_DIR/android-sdk-preview-license"
fi

# ── APK bauen ─────────────────────────────────────────────────────────────────
cd "$SCRIPT_DIR"
gradle assembleDebug

if [[ ! -f "$APK_SRC" ]]; then
    echo "❌ APK nicht gefunden — Build-Fehler oben prüfen"
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
