# Louis OS multi-provider routing

Louis OS must not depend on a single LLM provider.

Default routing order:
1. Groq for low-latency routine work.
2. OpenRouter for broad model choice and provider-side fallback.
3. Gemini direct for an independent Google path.
4. Mistral direct for a European independent path.

Configuration uses `LLM_PROVIDER_ORDER` as a comma-separated list. Each provider has dedicated environment variables: `<PROVIDER>_API_KEY`, `<PROVIDER>_BASE_URL`, and `<PROVIDER>_MODEL`. Existing `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_PROVIDER` remain supported as a backward-compatible single-provider profile.

Routing policy:
- try providers in configured order;
- never log API keys;
- continue after connection, rate-limit, edge-security or provider HTTP failures;
- return the first valid OpenAI-compatible response;
- raise one aggregated diagnostic only when all providers fail;
- preserve provider and model provenance in every response.

Recommended first production configuration:
`LLM_PROVIDER_ORDER=groq,openrouter,gemini,mistral`

Provider defaults:
- Groq: `https://api.groq.com/openai/v1`
- OpenRouter: `https://openrouter.ai/api/v1`
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai`
- Mistral: `https://api.mistral.ai/v1`
