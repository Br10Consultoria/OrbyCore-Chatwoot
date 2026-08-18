#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
stamp="$(date +%Y%m%d-%H%M%S)"
docker compose exec -T postgres pg_dump -U postgres -d chatwoot -Fc > "backups/chatwoot-${stamp}.dump"
find backups -type f -name 'chatwoot-*.dump' -mtime +30 -delete
echo "Backup criado: backups/chatwoot-${stamp}.dump"

