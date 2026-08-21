#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_health.sh
source scripts/_health.sh

[[ -f .env ]] || { echo "Arquivo .env não encontrado." >&2; exit 1; }
env_value() { sed -n "s/^$1=//p" .env | tail -n 1; }

domain="$(env_value CHATWOOT_DOMAIN)"
api_token="$(env_value CHATWOOT_API_TOKEN)"
agent_bot_id="$(env_value CHATWOOT_AGENT_BOT_ID)"
inbox_id="$(env_value CHATWOOT_INBOX_ID)"
[[ -n "$domain" && -n "$api_token" && -n "$agent_bot_id" && -n "$inbox_id" ]] || {
  echo "CHATWOOT_DOMAIN, CHATWOOT_API_TOKEN, CHATWOOT_AGENT_BOT_ID e CHATWOOT_INBOX_ID precisam estar configurados." >&2
  exit 1
}

echo "[1/5] Validando serviços..."
docker compose config --quiet
wait_for_bridge
docker compose ps
[[ -z "$(docker compose ps --status exited -q)" ]] || {
  echo "Há containers encerrados." >&2
  exit 1
}

echo "[2/5] Validando bridge e Redis..."
wait_for_public_bridge "https://${domain}/orby-bridge/ready"
dead_count="$(docker compose exec -T redis redis-cli -a "$(env_value REDIS_PASSWORD)" \
  --no-auth-warning LLEN orbybridge:webhooks:dead | tr -d '\r')"
[[ "$dead_count" == "0" ]] || {
  echo "Existem ${dead_count} webhook(s) na dead-letter." >&2
  exit 1
}

echo "[3/5] Validando vínculo e token do AgentBot..."
docker compose run --rm -T \
  -e ORBY_AGENT_BOT_ID="$agent_bot_id" \
  -e ORBY_INBOX_ID="$inbox_id" \
  -e ORBY_API_TOKEN="$api_token" \
  rails bundle exec rails runner '
    bot = AgentBot.find(ENV.fetch("ORBY_AGENT_BOT_ID"))
    inbox = Inbox.find(ENV.fetch("ORBY_INBOX_ID"))
    raise "AgentBot não está ativo nesta caixa" unless inbox.agent_bot_inbox&.active? && inbox.agent_bot == bot
    raise "Token da API não pertence ao AgentBot" unless bot.access_token&.token == ENV.fetch("ORBY_API_TOKEN")
    puts "AgentBot interativo validado: #{bot.id}"
  '

echo "[4/5] Validando configuração carregada pelo bridge..."
docker compose exec -T bridge python -c \
  "from app.config import get_settings; s=get_settings(); assert s.chatwoot_agent_bot_id == int('${agent_bot_id}'); print('AgentBot carregado pelo bridge:', s.chatwoot_agent_bot_id)"

echo "[5/5] Validando alcance do OrbyCore a partir do bridge..."
docker compose exec -T bridge python -c \
  "import os,urllib.request; urllib.request.urlopen(os.environ['ORBYCORE_API_URL'].rstrip('/') + '/health/', timeout=10)"

echo "Integração estrutural validada. Homologue ainda uma conversa real com /boleto, /status e /wifi."
