#!/bin/sh
# Fix permissions on mounted volumes (they're owned by root when first created).
# We run as root briefly, chown, then drop to appuser via gosu.
set -e

for dir in /cache /config; do
    if [ -d "$dir" ]; then
        chown -R appuser:appuser "$dir" 2>/dev/null || true
    else
        mkdir -p "$dir"
        chown -R appuser:appuser "$dir"
    fi
done

exec gosu appuser "$@"
