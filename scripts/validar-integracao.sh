#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_health.sh
source scripts/_health.sh

[[ -f .env ]] || { echo "Arquivo .env não encontrado." >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }

domain="$(env_value CHATWOOT_DOMAIN)"
api_token="$(env_value CHATWOOT_API_TOKEN)"
[[ -n "$domain" && -n "$api_token" ]] || {
  echo "CHATWOOT_DOMAIN e CHATWOOT_API_TOKEN precisam estar configurados." >&2
  exit 1
}

echo "[1/4] Validando serviços..."
docker compose config --quiet
wait_for_bridge
docker compose ps
[[ -z "$(docker compose ps --status exited -q)" ]] || {
  echo "Há containers encerrados." >&2
  exit 1
}

echo "[2/4] Validando bridge e Redis..."
wait_for_public_bridge "https://${domain}/orby-bridge/ready"
dead_count="$(docker compose exec -T redis redis-cli -a "$(env_value REDIS_PASSWORD)" \
  --no-auth-warning LLEN orbybridge:webhooks:dead | tr -d '\r')"
[[ "$dead_count" == "0" ]] || {
  echo "Existem ${dead_count} webhook(s) na dead-letter." >&2
  exit 1
}

echo "[3/4] Validando API autenticada do Chatwoot..."
curl -fsS -H "api_access_token: ${api_token}" "https://${domain}/api/v1/profile" >/dev/null

echo "[4/4] Validando alcance do OrbyCore a partir do bridge..."
docker compose exec -T bridge python -c \
  "import os,urllib.request; urllib.request.urlopen(os.environ['ORBYCORE_API_URL'].rstrip('/') + '/health/', timeout=10)"

echo "Integração estrutural validada. Homologue ainda uma conversa real com /boleto, /status e /wifi."
