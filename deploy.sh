#!/usr/bin/env bash
# Deploy PhotoFlow to LXC at your-server
# Usage: ./deploy.sh [--skip-migrate]
set -e

HOST="root@your-server"
DEST="/opt/photoflow"
DB_CONTAINER="photoflow-db-1"

echo "==> Packaging..."
tar czf /tmp/photoflow-deploy.tar.gz \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='frontend/dist' \
    -C "$(dirname "$0")" .

echo "==> Uploading..."
scp /tmp/photoflow-deploy.tar.gz "$HOST:/tmp/"
rm /tmp/photoflow-deploy.tar.gz

echo "==> Deploying on LXC..."
ssh "$HOST" bash -s <<'REMOTE'
set -e
mkdir -p /opt/photoflow
tar xzf /tmp/photoflow-deploy.tar.gz -C /opt/photoflow
rm /tmp/photoflow-deploy.tar.gz
cd /opt/photoflow
docker compose build --no-cache
docker compose up -d --remove-orphans
REMOTE

if [[ "$1" != "--skip-migrate" ]]; then
    echo "==> Running DB migration..."
    ssh "$HOST" bash -s <<'MIGRATE'
set -e
cd /opt/photoflow
# Wait for DB to be ready
sleep 3
docker compose exec -T db psql -U photoflow -d photoflow -f /dev/stdin < backend/migrate_v2.sql || true
MIGRATE
fi

echo "==> Done! PhotoFlow available at http://your-server:8090"
