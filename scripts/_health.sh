#!/usr/bin/env bash

wait_for_bridge() {
  local attempts="${1:-60}" attempt container_id state
  for attempt in $(seq 1 "$attempts"); do
    container_id="$(docker compose ps -q bridge)"
    if [[ -n "$container_id" ]]; then
      state="$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true)"
      if [[ "$state" == "running" ]] && docker compose exec -T bridge python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/ready', timeout=3)" \
        >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 2
  done

  echo "O bridge não ficou pronto dentro do prazo." >&2
  docker compose ps >&2
  docker compose logs --tail=150 bridge bridge-worker caddy >&2
  return 1
}

wait_for_public_bridge() {
  local url="$1" attempts="${2:-30}" attempt
  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      curl -fsS "$url"
      echo
      return 0
    fi
    sleep 2
  done

  echo "O endpoint público do bridge não respondeu dentro do prazo: $url" >&2
  docker compose logs --tail=100 bridge caddy >&2
  return 1
}
