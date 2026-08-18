#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only origin main
docker compose config --quiet
docker compose pull
docker compose build --pull bridge
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d --remove-orphans
docker image prune -f
docker compose ps

