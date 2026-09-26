# Qwen local provider on Google Cloud

This directory deploys `Qwen/Qwen2.5-7B-Instruct` behind vLLM's OpenAI-compatible API.

## 1. Create the API-key secret

```bash
openssl rand -hex 32 | gcloud secrets create local-llm-api-key \
  --project=test-bot-499814 \
  --data-file=-
```

If the secret already exists, add a version instead:

```bash
openssl rand -hex 32 | gcloud secrets versions add local-llm-api-key \
  --project=test-bot-499814 \
  --data-file=-
```

Keep a copy of the generated value temporarily because Louis OS must use the same value as `LOCAL_API_KEY`.

## 2. Deploy Qwen

From the repository root in Cloud Shell:

```bash
chmod +x deploy/local-llm/deploy.sh
PROJECT_ID=test-bot-499814 REGION=europe-west1 ./deploy/local-llm/deploy.sh
```

The script builds the container, deploys one NVIDIA L4 GPU with scale-to-zero, and prints the `/v1` base URL.

## 3. Test the model

```bash
LOCAL_URL="$(gcloud run services describe louis-local-llm \
  --project=test-bot-499814 --region=europe-west1 \
  --format='value(status.url)')"
LOCAL_KEY="$(gcloud secrets versions access latest \
  --project=test-bot-499814 --secret=local-llm-api-key)"

curl "$LOCAL_URL/v1/chat/completions" \
  -H "Authorization: Bearer $LOCAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-instruct","messages":[{"role":"user","content":"Réponds seulement: Qwen opérationnel"}],"max_tokens":32}'
```

## 4. Connect Louis OS

Update the existing Louis OS service:

```bash
gcloud run services update louis-os \
  --project=test-bot-499814 \
  --region=europe-west1 \
  --set-env-vars="LLM_PROVIDER_ORDER=groq,local,openrouter,gemini,mistral,LOCAL_BASE_URL=$LOCAL_URL/v1,LOCAL_MODEL=qwen2.5-7b-instruct" \
  --set-secrets="LOCAL_API_KEY=local-llm-api-key:latest"
```

Use `local,groq,...` instead if Qwen should be the primary model. The recommended initial order is `groq,local,...` so the GPU only wakes when Groq fails or when a dedicated test selects the local provider.

## Operational notes

- The first request after scale-to-zero can be slow because the container and model must start.
- `--max 1` prevents accidental parallel GPU cost growth.
- The endpoint is publicly reachable but requires the vLLM API key. A later hardening step can replace this with Cloud Run IAM plus Google identity-token authentication.
- Qwen is a fallback/local brain first; large multi-agent reports should still be benchmarked before making it the default.
