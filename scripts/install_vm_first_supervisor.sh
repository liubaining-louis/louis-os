#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${LOUIS_INSTALL_DIR:-/opt/louis-os}"
RESULTS_DIR="${LOUIS_RESULTS_DIR:-/var/lib/louis-os/results}"
SECRETS_DIR="${LOUIS_SECRETS_DIR:-/var/lib/louis-os/secrets}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-test-bot-499814}"

if [[ ! -x "${INSTALL_DIR}/scripts/vm_first_supervisor.sh" ]]; then
  chmod +x "${INSTALL_DIR}/scripts/vm_first_supervisor.sh"
fi

IMAGE="${LOUIS_IMAGE:-}"
if [[ -z "${IMAGE}" ]] && command -v curl >/dev/null 2>&1; then
  IMAGE="$(curl -fsS -H 'Metadata-Flavor: Google' \
    'http://metadata.google.internal/computeMetadata/v1/instance/attributes/louis-os-image' 2>/dev/null || true)"
fi
if [[ -z "${IMAGE}" ]]; then
  echo "Unable to resolve LOUIS_IMAGE from environment or VM metadata" >&2
  exit 1
fi

cat >/etc/systemd/system/louis-os-vm-first.service <<EOF
[Unit]
Description=Louis OS VM-first autonomous supervisor
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment=LOUIS_IMAGE=${IMAGE}
Environment=GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
Environment=LOUIS_RESULTS_DIR=${RESULTS_DIR}
Environment=LOUIS_SECRETS_DIR=${SECRETS_DIR}
ExecStart=${INSTALL_DIR}/scripts/vm_first_supervisor.sh
Restart=always
RestartSec=5
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable louis-os-vm-first.service
systemctl restart louis-os-vm-first.service
systemctl --no-pager --full status louis-os-vm-first.service
