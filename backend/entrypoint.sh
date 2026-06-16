#!/bin/sh
# Fix permissions on mounted volumes (they're owned by root when first created).
# We run as root briefly, chown, then drop to the target user via gosu.
#
# PHOTOFLOW_USER selects who the app process runs as (default: appuser). Set it
# to "root" for the services that write XMP/EXIF back into the photo library:
# those originals are root-owned (664 / dirs 755-775), so a uid-1000 process
# can't create exiftool's temp file in the directory. Running as root matches
# the file ownership and avoids re-chowning another app's (Immich) library.
set -e

TARGET_USER="${PHOTOFLOW_USER:-appuser}"
OWN_USER="$TARGET_USER"
[ "$TARGET_USER" = "root" ] && OWN_USER="root:root" || OWN_USER="appuser:appuser"

for dir in /cache /config /models; do
    if [ -d "$dir" ]; then
        chown -R "$OWN_USER" "$dir" 2>/dev/null || true
    else
        mkdir -p "$dir"
        chown -R "$OWN_USER" "$dir" 2>/dev/null || true
    fi
done

exec gosu "$TARGET_USER" "$@"
