#!/usr/bin/env bash
set -euo pipefail

# --- Standard labels for everything Simula touches ---
APP_LABEL_KEY="io.ecodia.simula"
JOB_LABEL_KEY="io.ecodia.job"
TTL_LABEL_KEY="io.ecodia.ttl"            # RFC3339 or duration hint
CREATED_LABEL_KEY="io.ecodia.created"    # RFC3339
APP_LABEL_VAL="true"
NETWORK_NAME="simula_net"

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

retry() { # retry <cmd...>
  local n=0 delay=1
  until "$@"; do
    n=$(( n + 1 ))
    if [ "$n" -ge 3 ]; then echo "retry: giving up on: $*" >&2; return 1; fi
    echo "retry: attempt $n failed, sleeping ${delay}s..." >&2
    sleep "$delay"; delay=$(( delay*2 ))
  done
}

ensure_builder() {
  docker buildx version >/dev/null 2>&1 || { echo "buildx missing"; return 1; }
  docker buildx inspect simula-builder >/dev/null 2>&1 || \
    docker buildx create --name simula-builder --driver docker-container --use
  docker buildx inspect --bootstrap >/dev/null
}

ensure_network() {
  docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || \
    docker network create --label "${APP_LABEL_KEY}=${APP_LABEL_VAL}" "$NETWORK_NAME"
}

# build <context> <tag> [job_id]
build() {
  local ctx="$1" tag="$2" job="${3:-job-$(date +%s)}"
  ensure_builder
  ensure_network
  retry docker buildx build "$ctx" \
    --pull \
    --label "${APP_LABEL_KEY}=${APP_LABEL_VAL}" \
    --label "${JOB_LABEL_KEY}=${job}" \
    --label "${CREATED_LABEL_KEY}=$(now_utc)" \
    --label "${TTL_LABEL_KEY}=$(now_utc)" \
    -t "$tag" \
    --load
}

# run <image:tag> <job_id> [-- args...]
run_job() {
  local image="$1" job="$2"; shift 2
  local name="simula-${job}-$(date +%s)"
  ensure_network
  retry docker run --pull=missing --rm --name "$name" \
    --label "${APP_LABEL_KEY}=${APP_LABEL_VAL}" \
    --label "${JOB_LABEL_KEY}=${job}" \
    --label "${CREATED_LABEL_KEY}=$(now_utc)" \
    --label "${TTL_LABEL_KEY}=$(now_utc)" \
    --network "$NETWORK_NAME" \
    -v /app:/workspace -w /workspace \
    "$image" "$@"
}

# gc [containers|images|networks|all]  (labels only)
gc() {
  local what="${1:-all}"
  if [[ "$what" == "containers" || "$what" == "all" ]]; then
    docker ps -aq --filter "label=${APP_LABEL_KEY}=${APP_LABEL_VAL}" | xargs -r docker rm -f
  fi
  if [[ "$what" == "images" || "$what" == "all" ]]; then
    docker images -q --filter "label=${APP_LABEL_KEY}=${APP_LABEL_VAL}" | xargs -r docker rmi -f
  fi
  if [[ "$what" == "networks" || "$what" == "all" ]]; then
    # only remove our labeled network if empty
    docker network ls --filter "label=${APP_LABEL_KEY}=${APP_LABEL_VAL}" -q | \
      xargs -r -I{} sh -c 'docker network inspect {} --format "{{ .Containers }}" | grep -q . || docker network rm {}'
  fi>
}

case "${1:-}" in
  ensure) ensure_builder; ensure_network ;;
  build)  build "$2" "$3" "${4:-}" ;;
  run)    run_job "$2" "$3" "${@:4}" ;;
  gc)     gc "${2:-all}" ;;
  *) echo "usage:
  $0 ensure
  $0 build <context> <tag> [job_id]
  $0 run <image:tag> <job_id> [-- args...]
  $0 gc [containers|images|networks|all]
"; exit 1 ;;
esac
