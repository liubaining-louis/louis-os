#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="${LOUIS_RESULTS_DIR:-/var/lib/louis-os/results}"
SECRETS_DIR="${LOUIS_SECRETS_DIR:-/var/lib/louis-os/secrets}"
IMAGE="${LOUIS_IMAGE:?LOUIS_IMAGE must point to the deployed louis-os-worker image}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-test-bot-499814}"
SUPERTEAM_ENV="${SECRETS_DIR}/superteam.env"

mkdir -p "${RESULTS_DIR}" "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

restart_container() {
  local name="$1"
  shift
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --name "$name" --restart unless-stopped "$@"
}

start_worker() {
  local env_args=()
  if [[ -s "${SUPERTEAM_ENV}" ]]; then
    env_args+=(--env-file "${SUPERTEAM_ENV}")
  fi
  restart_container louis-os-worker \
    "${env_args[@]}" \
    -e GOOGLE_CLOUD_PROJECT="${PROJECT_ID}" \
    -e LOUIS_VM_INTERVAL_SECONDS=300 \
    -e LOUIS_VM_HEARTBEAT_SECONDS=10 \
    -e LOUIS_LIVE_STATE_FIRESTORE=1 \
    -v "${RESULTS_DIR}:/app/results" \
    "${IMAGE}" \
    python scripts/vm_monetization_worker.py
}

start_browser_monitor() {
  restart_container louis-os-browser-monitor \
    -e GOOGLE_CLOUD_PROJECT="${PROJECT_ID}" \
    -e LOUIS_BROWSER_MONITOR_INTERVAL_SECONDS=300 \
    -e LOUIS_BROWSER_MONITOR_URL=https://app.manic.trade/pm \
    -v "${RESULTS_DIR}:/app/results" \
    "${IMAGE}" \
    python scripts/browser_vm_monitor.py
}

start_crypto_monitor() {
  restart_container louis-os-crypto-monitor \
    -e SOLANA_RPC_URL=https://api.mainnet-beta.solana.com \
    -v "${RESULTS_DIR}:/app/results" \
    "${IMAGE}" \
    sh -c 'while true; do python scripts/crypto_revenue_cycle.py || true; sleep 60; done'
}

ensure_running() {
  local name="$1"
  local starter="$2"
  if ! docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null | grep -qx true; then
    echo "[$(date -Is)] restarting $name"
    "$starter"
  fi
}

start_worker
start_browser_monitor
start_crypto_monitor

while true; do
  ensure_running louis-os-worker start_worker
  ensure_running louis-os-browser-monitor start_browser_monitor
  ensure_running louis-os-crypto-monitor start_crypto_monitor
  sleep 30
done
