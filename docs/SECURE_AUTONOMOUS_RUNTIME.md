# Secure autonomous runtime v1

This increment closes two production findings without claiming a higher maturity score.

## API authentication

`GET /` and `GET /health` remain public. The public dashboard does not receive an authenticated cookie. Every mission, memory, command, benchmark, provider and autonomous-cycle route remains protected.

An interactive dashboard user must explicitly exchange the configured API key for a short-lived, `HttpOnly`, `Secure`, `SameSite=Strict` cookie. The key is held only in the browser prompt and is not written to local or session storage.

Equivalent API clients should continue to send the key directly:

```bash
curl -H "X-Louis-Key: ${LOUIS_OS_API_KEY}" "${LOUIS_OS_URL}/missions?limit=1"
```

Production deployment fails if the public root emits a Louis session cookie or if an anonymous request to `/missions` does not return HTTP 401.

## Autonomous evidence durability

The monetization worker authenticates to Google Cloud through the repository's Workload Identity Federation variables before any Firestore use. Final-state synchronization is failure-isolated:

1. research and bounded execution run;
2. Firestore synchronization is attempted;
3. result and receipt files are committed even when synchronization fails;
4. the concise report is published;
5. the job ends in failure if Firestore was not synchronized.

This preserves audit evidence while keeping operational failure visible.

Only candidates with `readiness_status=executable_now` and `external_prerequisites_cleared=true` may become the projected top candidate. Gated opportunities remain counted but are never represented as autonomously executable.

## Promotion and rollback

Critical and high-severity remediations can pass the maturity gate without inflating a domain score. They require a unique remediation identifier, domain, finding, severity and verifiable evidence.
Remediation history is append-only, and new remediation evidence must be stronger than or equal to the affected domain evidence and include a reference not already used by the previous domain assessment.

Rollback is performed by reverting the increment. If authentication must be disabled urgently, remove public access to the Cloud Run service rather than restoring anonymous cookie issuance.
