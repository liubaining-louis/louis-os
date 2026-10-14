#!/usr/bin/env bash
set -euo pipefail

: "${LOCAL_LLM_API_KEY:?LOCAL_LLM_API_KEY must be configured}"

exec python3 -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --model "${MODEL_ID:-Qwen/Qwen2.5-7B-Instruct}" \
  --served-model-name "${SERVED_MODEL_NAME:-qwen2.5-7b-instruct}" \
  --dtype auto \
  --max-model-len "${MAX_MODEL_LEN:-8192}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.90}" \
  --api-key "${LOCAL_LLM_API_KEY}"
