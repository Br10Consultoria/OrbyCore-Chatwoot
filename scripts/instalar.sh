#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

generate_secret() {
  openssl rand -hex 48
}

ask() {
  local label="$1" default_value="${2:-}" answer=""
  if [[ -n "$default_value" ]]; then
    read -r -p "$label [$default_value]: " answer
    printf '%s' "${answer:-$default_value}"
  else
    read -r -p "$label: " answer
    printf '%s' "$answer"
  fi
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

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env

  echo ""
  echo "OrbyCore Chatwoot — configuração inicial"
  echo ""
  domain="$(ask "Domínio público do Chatwoot" "chat.exemplo.com.br")"
  sender="$(ask "E-mail remetente" "atendimento@${domain#*.}")"
  orbycore_url="$(ask "URL pública do OrbyCore" "https://erp.exemplo.com.br")"
  portal_url="$(ask "URL do Portal SAC" "${orbycore_url%/}/portal")"
  orbycore_token="$(ask_secret "ServiceToken gerado no OrbyCore")"

  if [[ -z "$domain" || -z "$orbycore_url" || -z "$orbycore_token" ]]; then
    echo "Domínio, URL do OrbyCore e ServiceToken são obrigatórios." >&2
    exit 1
  fi

  set_env CHATWOOT_DOMAIN "$domain"
  set_env FRONTEND_URL "https://$domain"
  set_env MAILER_SENDER_EMAIL "OrbyCore Atendimento <$sender>"
  set_env SECRET_KEY_BASE "$(generate_secret)$(generate_secret)"
  set_env POSTGRES_PASSWORD "$(generate_secret)"
  set_env REDIS_PASSWORD "$(generate_secret)"
  set_env BRIDGE_SERVICE_TOKEN "$(generate_secret)"
  set_env CHATWOOT_WEBHOOK_TOKEN "$(generate_secret)"
  set_env ORBYCORE_API_URL "$orbycore_url"
  set_env ORBYCORE_PORTAL_URL "$portal_url"
  set_env ORBYCORE_SERVICE_TOKEN "$orbycore_token"
fi

docker compose config --quiet
docker compose pull
docker compose build --pull bridge
docker compose up -d postgres redis
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d
docker compose ps

echo ""
echo "Etapa 1 concluída. Acesse https://${CHATWOOT_DOMAIN:-$(grep '^CHATWOOT_DOMAIN=' .env | cut -d= -f2-)} e crie o administrador e a caixa Website."
echo "Depois execute: sudo ./scripts/configurar-integracao.sh"
