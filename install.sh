#!/bin/bash
set -e

echo "🚀 PhotoFlow Installation"
echo "========================="

# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "❌ Docker ist nicht installiert. Bitte erst Docker installieren."; exit 1; }
command -v docker compose version >/dev/null 2>&1 || { echo "❌ Docker Compose ist nicht installiert."; exit 1; }

# Clone if not in directory
if [ ! -f "docker-compose.yml" ]; then
  git clone https://github.com/user/photoflow .
fi

# Create .env if missing
if [ ! -f ".env" ]; then
  cp .env.example .env
  # Generate random secrets
  DB_PASS=$(openssl rand -hex 24)
  SECRET=$(openssl rand -hex 32)
  sed -i "s/change_me_strong_password/$DB_PASS/g" .env
  sed -i "s/change_me_very_long_random_string_at_least_32_chars/$SECRET/g" .env
  echo "✅ .env erstellt mit zufälligen Passwörtern"
  echo ""
  echo "📝 Bitte passe PHOTOS_PATH in .env an:"
  echo "   PHOTOS_PATH=/dein/foto/pfad"
  echo ""
  read -p "Drücke Enter um fortzufahren (oder Ctrl+C zum Abbrechen)..."
fi

# Pull and start
docker compose pull
docker compose up -d

echo ""
echo "✅ PhotoFlow läuft auf http://localhost:$(grep PORT .env | cut -d= -f2 | tr -d ' ' || echo 8090)"
echo ""
echo "📷 Füge deinen Foto-Ordner unter Einstellungen → Quellen hinzu."
