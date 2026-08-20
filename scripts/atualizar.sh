#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Instalação existente sem .env; atualização cancelada." >&2; exit 1; }
echo "[OrbyChat] Backup obrigatório antes da atualização..."
backup_log="$(mktemp)"
trap 'rm -f -- "$backup_log"' EXIT
./scripts/backup.sh | tee "$backup_log"
backup_dir="$(sed -n 's/^Backup verificado: //p' "$backup_log" | tail -n 1)"
[[ -n "$backup_dir" && -s "$backup_dir/storage.tar.gz" ]] || {
  echo "Não foi possível localizar o backup verificado dos anexos." >&2
  exit 1
}

git pull --ff-only origin main
docker compose config --quiet
docker compose pull
docker compose build --pull bridge bridge-worker
echo "[OrbyChat] Migrando anexos para o volume persistente..."
docker compose stop rails sidekiq
docker compose run --rm --no-deps -T --entrypoint sh rails -c \
  'find /app/storage -mindepth 1 -delete && tar -C /app/storage -xzf -' \
  < "$backup_dir/storage.tar.gz"
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d --remove-orphans
docker image prune -f
docker compose ps

