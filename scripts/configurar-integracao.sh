#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "Execute scripts/instalar.sh primeiro." >&2; exit 1; }

ask() {
  local label="$1" default_value="${2:-}" answer=""
  read -r -p "$label${default_value:+ [$default_value]}: " answer
  printf '%s' "${answer:-$default_value}"
}

ask_secret() {
  local label="$1" answer=""
  read -r -s -p "$label: " answer
  echo >&2
  printf '%s' "$answer"
}

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

echo ""
echo "Vinculação Chatwoot ↔ OrbyCore"
echo "Os valores abaixo são obtidos no painel do Chatwoot depois da criação do administrador."
echo ""

account_id="$(ask "Account ID" "1")"
inbox_id="$(ask "Inbox ID da caixa Portal SAC" "1")"
api_token="$(ask_secret "API Access Token do usuário de integração")"
website_token="$(ask_secret "Website Token da caixa Portal SAC")"
hmac_token="$(ask_secret "HMAC Token de Identity Validation")"

if [[ -z "$api_token" || -z "$website_token" || -z "$hmac_token" ]]; then
  echo "API Access Token, Website Token e HMAC Token são obrigatórios." >&2
  exit 1
fi

set_env CHATWOOT_ACCOUNT_ID "$account_id"
set_env CHATWOOT_INBOX_ID "$inbox_id"
set_env CHATWOOT_API_TOKEN "$api_token"
set_env CHATWOOT_INBOX_IDENTIFIER "$website_token"
set_env CHATWOOT_INBOX_HMAC_TOKEN "$hmac_token"

docker compose config --quiet
docker compose up -d --build --force-recreate bridge bridge-worker caddy

domain="$(grep '^CHATWOOT_DOMAIN=' .env | cut -d= -f2-)"
webhook_token="$(grep '^CHATWOOT_WEBHOOK_TOKEN=' .env | cut -d= -f2-)"

echo ""
echo "Vinculação gravada. Cadastre no Chatwoot o webhook:"
echo "https://${domain}/orby-bridge/v1/chatwoot/webhooks/${webhook_token}"
echo "Eventos: message_created, conversation_created e conversation_status_changed."
echo ""
echo "Validação local:"
echo "curl -fsS https://${domain}/orby-bridge/ready"
echo ""
echo "Para habilitar o widget, copie BRIDGE_SERVICE_TOKEN do .env desta VM para"
echo "CHATWOOT_BRIDGE_SERVICE_TOKEN no .env do OrbyCore e configure:"
echo "CHATWOOT_BRIDGE_URL=https://${domain}/orby-bridge"
