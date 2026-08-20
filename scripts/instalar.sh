#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

ensure_runtime() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    systemctl enable --now docker >/dev/null 2>&1 || true
    return
  fi
  [[ "$EUID" -eq 0 ]] || {
    echo "Execute o instalador com sudo para instalar Docker e Compose." >&2
    exit 1
  }
  [[ -r /etc/os-release ]] || {
    echo "Não foi possível identificar o sistema operacional." >&2
    exit 1
  }
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) docker_distribution="$ID" ;;
    *)
      echo "Instalação automática suportada somente em Ubuntu e Debian." >&2
      echo "Instale Docker Engine e o plugin Compose e execute novamente." >&2
      exit 1
      ;;
  esac

  echo "[OrbyChat] Instalando Docker Engine e Docker Compose pelo repositório oficial..."
  apt-get update
  apt-get install -y ca-certificates curl git openssl python3
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${docker_distribution}/gpg" \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  docker_suite="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  [[ -n "$docker_suite" ]] || {
    echo "Codename da distribuição não encontrado." >&2
    exit 1
  }
  printf '%s\n' \
    'Types: deb' \
    "URIs: https://download.docker.com/linux/${docker_distribution}" \
    "Suites: ${docker_suite}" \
    'Components: stable' \
    "Architectures: $(dpkg --print-architecture)" \
    'Signed-By: /etc/apt/keyrings/docker.asc' \
    > /etc/apt/sources.list.d/docker.sources
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  docker info >/dev/null
  docker compose version
}

ensure_runtime

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

wait_for_services() {
  local services=(postgres redis rails sidekiq bridge bridge-worker caddy)
  local attempt service container_id state health pending
  for attempt in $(seq 1 120); do
    pending=0
    for service in "${services[@]}"; do
      container_id="$(docker compose ps -q "$service")"
      if [[ -z "$container_id" ]]; then
        pending=1
        continue
      fi
      state="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
      if [[ "$health" == "unhealthy" || "$state" == "exited" || "$state" == "dead" ]]; then
        echo "O serviço $service falhou durante a inicialização." >&2
        docker compose logs --tail=100 "$service" >&2
        return 1
      elif [[ "$state" != "running" || "$health" == "starting" ]]; then
        pending=1
      fi
    done
    [[ "$pending" -eq 0 ]] && return 0
    sleep 5
  done
  echo "Tempo limite aguardando os serviços." >&2
  docker compose ps >&2
  docker compose logs --tail=100 rails bridge bridge-worker caddy >&2
  return 1
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
docker compose build --pull bridge bridge-worker
docker compose up -d postgres redis
docker compose run --rm rails bundle exec rails db:chatwoot_prepare
docker compose up -d
wait_for_services
docker compose ps

echo ""
echo "Etapa 1 concluída. Acesse https://${CHATWOOT_DOMAIN:-$(grep '^CHATWOOT_DOMAIN=' .env | cut -d= -f2-)} e crie o administrador e a caixa Website."
echo "Depois execute: sudo ./scripts/configurar-integracao.sh"
