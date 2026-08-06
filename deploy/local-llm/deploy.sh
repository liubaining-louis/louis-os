#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-test-bot-499814}"
REGION="${REGION:-europe-west1}"
SERVICE_NAME="${SERVICE_NAME:-louis-local-llm}"
REPOSITORY="${REPOSITORY:-louis-os}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:latest"
SECRET_NAME="${SECRET_NAME:-local-llm-api-key}"

command -v gcloud >/dev/null || { echo "gcloud is required" >&2; exit 1; }

gcloud config set project "${PROJECT_ID}"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe "${REPOSITORY}" --location "${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${REPOSITORY}" --repository-format=docker --location "${REGION}"

gcloud builds submit deploy/local-llm --tag "${IMAGE}"

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --execution-environment gen2 \
  --gpu 1 \
  --gpu-type nvidia-l4 \
  --cpu 8 \
  --memory 32Gi \
  --concurrency 4 \
  --min 0 \
  --max 1 \
  --timeout 900 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --set-secrets LOCAL_LLM_API_KEY="${SECRET_NAME}:latest" \
  --set-env-vars MODEL_ID=Qwen/Qwen2.5-7B-Instruct,SERVED_MODEL_NAME=qwen2.5-7b-instruct,MAX_MODEL_LEN=8192,GPU_MEMORY_UTILIZATION=0.90

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')"
echo "Qwen service: ${SERVICE_URL}/v1"
echo "Configure Louis OS with LOCAL_BASE_URL=${SERVICE_URL}/v1 and LOCAL_MODEL=qwen2.5-7b-instruct"
