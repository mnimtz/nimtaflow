#!/bin/bash
# Build, archive, export und upload NimtaFlow tvOS zu App Store Connect.
# Voraussetzung: ASC_KEY_ID + ASC_ISSUER_ID gesetzt (AuthKey liegt unter ~/.appstoreconnect/).
set -euo pipefail
cd "$(dirname "$0")"

SCHEME=NimtaFlowTV
PROJECT=NimtaFlowTV.xcodeproj
ARCHIVE=build/NimtaFlowTV.xcarchive
EXPORT=build/export-tv
EXPORT_OPTS=ExportOptions-appletv.plist

BUILD=$(date +%Y%m%d%H%M)
KEY=~/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8
echo "▶︎ tvOS Build number: $BUILD"

xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=tvOS' \
  -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  CODE_SIGN_STYLE=Manual \
  DEVELOPMENT_TEAM=KQGPPH4S33 \
  CODE_SIGN_IDENTITY="Apple Distribution" \
  PROVISIONING_PROFILE_SPECIFIER="NimtaFlow tvOS AppStore" \
  CURRENT_PROJECT_VERSION="$BUILD" clean archive

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportOptionsPlist "$EXPORT_OPTS" \
  -exportPath "$EXPORT" \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"

IPA=$(ls "$EXPORT"/*.ipa 2>/dev/null | head -1)
echo "▶︎ Built: ${IPA:-KEIN IPA}"

if [ -n "${IPA:-}" ] && [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" ]]; then
  echo "▶︎ Uploading to App Store Connect…"
  xcrun altool --upload-app -f "$IPA" -t appletvos \
    --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
  echo "✓ Upload OK"
fi
