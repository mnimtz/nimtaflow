#!/bin/bash
# Build, archive, export and upload PhotoFlow to TestFlight.
#
# ONE-TIME credential setup (the only step Claude can't do for you — it needs
# your App Store Connect API key, which must not be shared):
#   1. App Store Connect → Users and Access → Integrations → App Store Connect API
#      → create a key with role "App Manager". Note the Key ID and Issuer ID,
#      download the AuthKey_XXXX.p8.
#   2. Put the .p8 at ~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8
#   3. export ASC_KEY_ID=...  ASC_ISSUER_ID=...
#
# Then just run:  ./testflight.sh
#
# First also create the app record once in App Store Connect with bundle id
# email.nimtz.photoflow (Apps → + → New App). After that, every run here uploads a
# new build to TestFlight.
set -euo pipefail
cd "$(dirname "$0")"

SCHEME=PhotoFlow
PROJECT=PhotoFlow.xcodeproj
ARCHIVE=build/PhotoFlow.xcarchive
EXPORT=build/export

# Auto-bump the build number so each upload is unique (TestFlight requirement).
BUILD=$(date +%Y%m%d%H%M)
echo "▶︎ Build number: $BUILD"

xcodebuild -project "$PROJECT" -scheme "$SCHEME" \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE" \
  CURRENT_PROJECT_VERSION="$BUILD" \
  clean archive

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE" \
  -exportOptionsPlist ExportOptions.plist \
  -exportPath "$EXPORT"

IPA=$(ls "$EXPORT"/*.ipa | head -1)
echo "▶︎ Built: $IPA"

if [[ -n "${ASC_KEY_ID:-}" && -n "${ASC_ISSUER_ID:-}" ]]; then
  echo "▶︎ Uploading to TestFlight…"
  xcrun altool --upload-app -f "$IPA" -t ios \
    --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
  echo "✓ Uploaded. It appears in TestFlight after Apple finishes processing (~5–15 min)."
else
  echo "ℹ︎ IPA exported but NOT uploaded (set ASC_KEY_ID / ASC_ISSUER_ID to upload)."
  echo "  Or drag $IPA into Transporter.app to upload manually."
fi
