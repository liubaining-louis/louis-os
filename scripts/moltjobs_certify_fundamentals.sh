#!/usr/bin/env bash
set -euo pipefail

export MOLT_NO_UPDATE_CHECK=1
export OLLAMA_HOST=http://127.0.0.1:11434
export MOLTJOBS_API_KEY="$(cat /var/lib/louis-os/secrets/moltjobs_api_key)"
STATE_DIR=/var/lib/louis-os/state
RESULT="$STATE_DIR/moltjobs_general_fundamentals_result.json"
STDERR_FILE="$STATE_DIR/moltjobs_general_fundamentals_stderr.log"
PACK_ID=d9539439-c7c1-4c0b-ac72-71480038d395
mkdir -p "$STATE_DIR"

cleanup() {
  unset MOLTJOBS_API_KEY || true
}
trap cleanup EXIT

test -s /var/lib/louis-os/secrets/moltjobs_api_key
test -f /opt/moltjobs-evals/dist/cli.js
command -v ollama >/dev/null 2>&1
systemctl start ollama >/dev/null 2>&1 || true
for _ in $(seq 1 30); do
  curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null
ollama list | grep -q 'qwen2.5:3b'

BEFORE="$(louis-molt agent me --json)"
printf '%s' "$BEFORE" >"$STATE_DIR/moltjobs_agent_before_cert.json"
if printf '%s' "$BEFORE" | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("passedFundamentals") else 1)'; then
  echo 'MOLTJOBS_FUNDAMENTALS_ALREADY_PASSED=true'
  exit 0
fi

cd /opt/moltjobs-evals
set +e
node dist/cli.js run \
  --pack "$PACK_ID" \
  --solver ollama:qwen2.5:3b \
  --mode CLOSED_BOOK \
  --json \
  >"$RESULT" 2>"$STDERR_FILE"
RC=$?
set -e

echo "MOLTJOBS_EVAL_EXIT_CODE=$RC"
python3 - "$RESULT" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if p.exists() and p.stat().st_size:
    try:
        d = json.loads(p.read_text())
        report = d.get('report') or d
        safe = {
            'quizId': d.get('quizId') or report.get('quizId'),
            'score': report.get('score'),
            'passed': report.get('passed'),
            'certification': report.get('certification') or report.get('cert'),
        }
        print('MOLTJOBS_EVAL_SAFE_RESULT=' + json.dumps(safe, separators=(',', ':')))
    except Exception as e:
        print('MOLTJOBS_EVAL_RESULT_PARSE_ERROR=' + type(e).__name__)
else:
    print('MOLTJOBS_EVAL_RESULT_MISSING=true')
PY

AFTER="$(louis-molt agent me --json)"
printf '%s' "$AFTER" >"$STATE_DIR/moltjobs_agent_after_cert.json"
printf '%s' "$AFTER" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("MOLTJOBS_AGENT_STATUS="+str(d.get("status"))); print("MOLTJOBS_PASSED_FUNDAMENTALS="+str(bool(d.get("passedFundamentals"))).lower()); print("MOLTJOBS_CERTIFIED_AT="+str(d.get("certifiedAt"))); raise SystemExit(0 if d.get("passedFundamentals") else 3)'
