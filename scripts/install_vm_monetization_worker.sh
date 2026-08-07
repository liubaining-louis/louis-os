#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${LOUIS_REPO_DIR:-/opt/louis-os}"
SERVICE_NAME="louis-os-monetization.service"
SERVICE_SRC="$REPO_DIR/deploy/$SERVICE_NAME"
SERVICE_DST="/etc/systemd/system/$SERVICE_NAME"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "Expected Louis OS checkout at $REPO_DIR" >&2
  exit 1
fi

cd "$REPO_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .

sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME"
