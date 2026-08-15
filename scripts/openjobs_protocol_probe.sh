#!/usr/bin/env bash
set -euo pipefail
OUT='/var/lib/louis-os/results/openjobs-probe'
mkdir -p "$OUT"

curl -fsSL --max-time 30 https://openjobs.bot/skill.md -o "$OUT/skill.md"
curl -fsSL --max-time 30 https://openjobs.bot/heartbeat.md -o "$OUT/heartbeat.md" || true

echo '=== PROTOCOL SIGNALS ==='
grep -Ein 'register|login|api.?key|terms|wallet|stake|deposit|apply|submit|jobs|usdc|wage|claim|sign|auth' "$OUT/skill.md" | head -n 260 || true

echo '=== HEARTBEAT SIGNALS ==='
grep -Ein 'register|login|api.?key|wallet|stake|deposit|apply|submit|jobs|usdc|wage|claim|sign|auth' "$OUT/heartbeat.md" | head -n 180 || true

echo '=== ENDPOINT CANDIDATES ==='
grep -Eo 'https://openjobs\.bot[^` )]+' "$OUT/skill.md" | sort -u | head -n 120 || true
grep -Eo '/api/[A-Za-z0-9_/?=&.{}:-]+' "$OUT/skill.md" | sort -u | head -n 180 || true

echo '=== DOCUMENT HASHES ==='
sha256sum "$OUT/skill.md" "$OUT/heartbeat.md" 2>/dev/null || true

echo 'OPENJOBS_PROTOCOL_PROBE_COMPLETE=true'
