#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

backup_dir="${1:-}"
[[ -n "$backup_dir" && -d "$backup_dir" ]] || {
  echo "Uso: $0 backups/AAAAMMDD-HHMMSS [--yes]" >&2
  exit 1
}
[[ -s "$backup_dir/chatwoot.dump" && -s "$backup_dir/storage.tar.gz" ]] || {
  echo "Backup incompleto." >&2
  exit 1
}
(cd "$backup_dir" && sha256sum --check SHA256SUMS)

if [[ "${2:-}" != "--yes" ]]; then
  read -r -p "A restauração substituirá banco e anexos. Digite RESTAURAR: " confirmation
  [[ "$confirmation" == "RESTAURAR" ]] || { echo "Cancelado."; exit 1; }
fi

docker compose stop rails sidekiq bridge bridge-worker
docker compose exec -T postgres dropdb -U postgres --if-exists --force chatwoot
docker compose exec -T postgres createdb -U postgres chatwoot
docker compose exec -T postgres pg_restore -U postgres -d chatwoot --no-owner --no-privileges \
  < "$backup_dir/chatwoot.dump"
docker compose run --rm --no-deps -T --entrypoint sh rails -c \
  'find /app/storage -mindepth 1 -delete && tar -C /app/storage -xzf -' \
  < "$backup_dir/storage.tar.gz"
docker compose up -d rails sidekiq bridge bridge-worker caddy
echo "Restauração concluída a partir de $backup_dir"
