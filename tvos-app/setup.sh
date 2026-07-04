#!/usr/bin/env bash
# NimtaFlowTV — Xcode-Projekt aus project.yml generieren
# Einmalig ausführen nachdem du diesen Ordner geklont hast.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "▸ NimtaFlowTV — Xcode-Projekt einrichten"
echo ""

# XcodeGen installieren falls nötig
if ! command -v xcodegen &>/dev/null; then
    echo "▸ XcodeGen installieren (benötigt Homebrew)..."
    brew install xcodegen
fi

echo "▸ Projekt generieren..."
xcodegen generate

echo ""
echo "✓ Fertig! Nächste Schritte:"
echo ""
echo "  1. Xcode öffnen:"
echo "     open NimtaFlowTV.xcodeproj"
echo ""
echo "  2. In Xcode: Target 'NimtaFlowTV' → Signing & Capabilities → Team setzen"
echo ""
echo "  3. Simulator wählen: 'Apple TV' → ▶ Run (⌘R)"
echo ""
echo "  Für echtes Apple TV: Device über USB/HDMI verbinden, in Xcode auswählen"
