#!/usr/bin/env bash
set -euo pipefail

RUNTIME_USER="${LOUIS_RUNTIME_USER:-louis-os}"
RUNTIME_GROUP="${LOUIS_RUNTIME_GROUP:-louis-runtime}"
BASE=/var/lib/louis-os

getent group "$RUNTIME_GROUP" >/dev/null || groupadd --system "$RUNTIME_GROUP"
id -u "$RUNTIME_USER" >/dev/null 2>&1 || useradd --system --gid "$RUNTIME_GROUP" --home-dir "$BASE" --shell /usr/sbin/nologin "$RUNTIME_USER"

# Runtime can traverse to explicitly known allow-listed secret files but cannot list
# the entire secret directory.
install -d -m 710 -o root -g "$RUNTIME_GROUP" "$BASE/secrets"
for dir in state results runtime config; do
  install -d -m 770 -o "$RUNTIME_USER" -g "$RUNTIME_GROUP" "$BASE/$dir"
done
install -d -m 770 -o "$RUNTIME_USER" -g "$RUNTIME_GROUP" "$BASE/results/taskforce"

# Explicit allow-list only: never grant the runtime account blanket read access to all secrets.
for secret in "$BASE/secrets/moltjobs_api_key" "$BASE/secrets/taskforce.env"; do
  if [[ -e "$secret" ]]; then
    chown root:"$RUNTIME_GROUP" "$secret"
    chmod 640 "$secret"
  fi
done

# Existing runtime state becomes owned by the non-login runtime identity.
for path in "$BASE/state" "$BASE/results/taskforce"; do
  chown -R "$RUNTIME_USER":"$RUNTIME_GROUP" "$path"
  chmod -R u+rwX,g+rwX,o-rwx "$path"
done

echo "LOUIS_RUNTIME_HARDENING_READY=true"
echo "LOUIS_RUNTIME_USER=$RUNTIME_USER"
echo "LOUIS_RUNTIME_GROUP=$RUNTIME_GROUP"
