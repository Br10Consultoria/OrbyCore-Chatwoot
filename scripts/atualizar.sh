#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Instalação existente sem .env; atualização cancelada." >&2; exit 1; }
echo "[OrbyChat] Backup obrigatório antes da atualização..."
./scripts/backup.sh

git pull --ff-only origin main
docker compose config --quiet
docker compose pull
docker compose build --pull bridge bridge-worker
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d --remove-orphans
docker image prune -f
docker compose ps

