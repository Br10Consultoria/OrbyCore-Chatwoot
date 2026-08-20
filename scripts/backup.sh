#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Arquivo .env não encontrado." >&2; exit 1; }
mkdir -p backups
stamp="$(date +%Y%m%d-%H%M%S)"
backup_dir="backups/${stamp}"
mkdir -p "$backup_dir"

echo "[OrbyChat] Exportando PostgreSQL..."
docker compose exec -T postgres pg_dump -U postgres -d chatwoot -Fc > "$backup_dir/chatwoot.dump"
[[ -s "$backup_dir/chatwoot.dump" ]] || { echo "Dump PostgreSQL vazio." >&2; exit 1; }
docker compose exec -T postgres pg_restore --list < "$backup_dir/chatwoot.dump" >/dev/null

echo "[OrbyChat] Exportando anexos do Active Storage..."
docker compose run --quiet-pull --rm --no-deps -T --entrypoint tar rails \
  -C /app/storage -czf - . > "$backup_dir/storage.tar.gz"
[[ -s "$backup_dir/storage.tar.gz" ]] || { echo "Backup do storage vazio." >&2; exit 1; }
tar -tzf "$backup_dir/storage.tar.gz" >/dev/null

(
  cd "$backup_dir"
  sha256sum chatwoot.dump storage.tar.gz > SHA256SUMS
  sha256sum --check SHA256SUMS >/dev/null
)
printf 'created_at=%s\nchatwoot_image=%s\n' \
  "$(date --iso-8601=seconds)" \
  "$(docker compose images rails --format json 2>/dev/null | head -n 1)" \
  > "$backup_dir/manifest.txt"

find backups -mindepth 2 -maxdepth 2 -type f -mtime +"${BACKUP_RETENTION_DAYS:-30}" -delete
find backups -mindepth 1 -maxdepth 1 -type d -empty -delete
echo "Backup verificado: $backup_dir"

