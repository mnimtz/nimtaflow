#!/bin/bash
set -euo pipefail
SCHEME=PhotoFlow; PROJECT=PhotoFlow.xcodeproj
ARCHIVE=build/PhotoFlow-mac.xcarchive; EXPORT=build/export-mac
BUILD=$(date +%Y%m%d%H%M)
KEY=~/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8
echo "▶︎ Mac Build number: $BUILD"
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=macOS,variant=Mac Catalyst' \
  -archivePath "$ARCHIVE" \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID" \
  CURRENT_PROJECT_VERSION="$BUILD" clean archive
xcodebuild -exportArchive -archivePath "$ARCHIVE" \
  -exportOptionsPlist ExportOptions-mac-manual.plist -exportPath "$EXPORT" \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$KEY" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"
PKG=$(ls "$EXPORT"/*.pkg 2>/dev/null | head -1)
echo "▶︎ Built: ${PKG:-KEIN PKG}"
[ -n "${PKG:-}" ] && xcrun altool --upload-app -f "$PKG" -t macos --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" && echo "✓ Mac-Upload OK"
