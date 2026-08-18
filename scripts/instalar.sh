#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Arquivo .env criado. Preencha os segredos e execute novamente."
  exit 1
fi

docker compose config --quiet
docker compose pull
docker compose build --pull bridge
docker compose up -d postgres redis
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d
docker compose ps

