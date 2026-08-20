#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_health.sh
source scripts/_health.sh

[[ -f .env ]] || { echo "Execute scripts/instalar.sh primeiro." >&2; exit 1; }

set_env() {
  ENV_KEY="$1" ENV_VALUE="$2" python3 - <<'PY'
import os
from pathlib import Path

path = Path(".env")
key = os.environ["ENV_KEY"]
value = os.environ["ENV_VALUE"].replace("\r", "").replace("\n", "")
lines = path.read_text(encoding="utf-8").splitlines()
entry = f"{key}={value}"
for index, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[index] = entry
        break
else:
    lines.append(entry)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

env_value() {
  sed -n "s/^$1=//p" .env | tail -n 1
}

json_value() {
  CONFIG_JSON="$1" CONFIG_KEY="$2" python3 - <<'PY'
import json
import os

print(json.loads(os.environ["CONFIG_JSON"])[os.environ["CONFIG_KEY"]])
PY
}

echo ""
echo "Vinculação Chatwoot ↔ OrbyCore"
echo "A caixa, usuário técnico, HMAC, tokens, agente e webhook serão configurados automaticamente."
echo ""

domain="$(env_value CHATWOOT_DOMAIN)"
portal_url="$(env_value ORBYCORE_PORTAL_URL)"
webhook_token="$(env_value CHATWOOT_WEBHOOK_TOKEN)"
account_id="$(env_value CHATWOOT_ACCOUNT_ID)"
inbox_name="${CHATWOOT_INBOX_NAME:-Portal Sac}"
integration_email="${CHATWOOT_INTEGRATION_EMAIL:-orby-integracao@${domain}}"
widget_color="$(env_value CHATWOOT_WIDGET_COLOR)"
widget_title="$(env_value CHATWOOT_WIDGET_WELCOME_TITLE)"
widget_tagline="$(env_value CHATWOOT_WIDGET_WELCOME_TAGLINE)"
widget_color="${widget_color:-#087FAE}"
widget_title="${widget_title:-Olá! Como podemos ajudar?}"
widget_tagline="${widget_tagline:-Suporte técnico, financeiro e contratação em um só lugar.}"
rotate_hmac="${ROTATE_CHATWOOT_HMAC:-false}"
rotate_webhook="${ROTATE_CHATWOOT_WEBHOOK:-false}"

if [[ "$rotate_webhook" == "true" ]]; then
  webhook_token="$(openssl rand -hex 48)"
  set_env CHATWOOT_WEBHOOK_TOKEN "$webhook_token"
fi

if [[ -z "$domain" || -z "$portal_url" || -z "$webhook_token" ]]; then
  echo "CHATWOOT_DOMAIN, ORBYCORE_PORTAL_URL e CHATWOOT_WEBHOOK_TOKEN são obrigatórios." >&2
  exit 1
fi

webhook_url="https://${domain}/orby-bridge/v1/chatwoot/webhooks/${webhook_token}"
runner_output="$(docker compose exec -T \
  -e ORBY_ACCOUNT_ID="$account_id" \
  -e ORBY_INBOX_NAME="$inbox_name" \
  -e ORBY_PORTAL_URL="$portal_url" \
  -e ORBY_WEBHOOK_URL="$webhook_url" \
  -e ORBY_INTEGRATION_EMAIL="$integration_email" \
  -e ORBY_WIDGET_COLOR="$widget_color" \
  -e ORBY_WIDGET_WELCOME_TITLE="$widget_title" \
  -e ORBY_WIDGET_WELCOME_TAGLINE="$widget_tagline" \
  -e ORBY_ROTATE_HMAC="$rotate_hmac" \
  rails bundle exec rails runner - < scripts/automatizar-chatwoot.rb)"

config_json="$(printf '%s\n' "$runner_output" | sed -n 's/^ORBYCHAT_CONFIG=//p' | tail -n 1)"
if [[ -z "$config_json" ]]; then
  echo "$runner_output" >&2
  echo "O Chatwoot não retornou os dados da vinculação." >&2
  exit 1
fi

account_id="$(json_value "$config_json" account_id)"
inbox_id="$(json_value "$config_json" inbox_id)"
api_token="$(json_value "$config_json" api_token)"
website_token="$(json_value "$config_json" website_token)"
hmac_token="$(json_value "$config_json" hmac_token)"
integration_email="$(json_value "$config_json" integration_email)"
webhook_id="$(json_value "$config_json" webhook_id)"
team_support_id="$(json_value "$config_json" team_support_id)"
team_financial_id="$(json_value "$config_json" team_financial_id)"
team_commercial_id="$(json_value "$config_json" team_commercial_id)"

set_env CHATWOOT_ACCOUNT_ID "$account_id"
set_env CHATWOOT_INBOX_ID "$inbox_id"
set_env CHATWOOT_API_TOKEN "$api_token"
set_env CHATWOOT_INBOX_IDENTIFIER "$website_token"
set_env CHATWOOT_INBOX_HMAC_TOKEN "$hmac_token"
set_env CHATWOOT_TEAM_SUPPORT_ID "$team_support_id"
set_env CHATWOOT_TEAM_FINANCIAL_ID "$team_financial_id"
set_env CHATWOOT_TEAM_COMMERCIAL_ID "$team_commercial_id"

docker compose config --quiet
docker compose build bridge bridge-worker
docker compose up -d --force-recreate --no-deps bridge bridge-worker caddy
wait_for_bridge
wait_for_public_bridge "https://${domain}/orby-bridge/ready"

echo ""
echo "Vinculação concluída automaticamente."
echo "Conta: ${account_id} | Caixa: ${inbox_id} | Webhook: ${webhook_id}"
echo "Equipes: Suporte ${team_support_id} | Financeiro ${team_financial_id} | Comercial ${team_commercial_id}"
echo "Usuário técnico: ${integration_email}"
echo "URL do webhook: ${webhook_url}"
echo ""
echo "Bridge interno e endpoint público validados."
echo ""
echo "Para habilitar o widget, copie BRIDGE_SERVICE_TOKEN do .env desta VM para"
echo "CHATWOOT_BRIDGE_SERVICE_TOKEN no .env do OrbyCore e configure:"
echo "CHATWOOT_BRIDGE_URL=https://${domain}/orby-bridge"
