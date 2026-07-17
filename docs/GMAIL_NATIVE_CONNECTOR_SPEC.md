# Native Gmail Connector Specification

## Scope
Read-only Gmail ingestion for Louis OS. The connector may search messages, read threads and attachments metadata, and emit bounded evidence bundles. It may not send, delete, archive, label or modify messages.

## Authentication
- OAuth 2.0 refresh token or workload-compatible delegated credential.
- Secrets stored only in Google Secret Manager.
- Minimum Gmail scope: `https://www.googleapis.com/auth/gmail.readonly`.
- No tokens, credentials or raw authorization headers in logs, Firestore records, prompts or GitHub issues.

## Evidence output
Each message or thread is normalized to:

```json
{
  "source": "gmail",
  "reference": "gmail-thread:<thread_id>",
  "content": "bounded plain-text summary or body",
  "metadata": {
    "subject": "...",
    "from": "...",
    "to": ["..."],
    "date": "...",
    "message_ids": ["..."]
  }
}
```

## Guardrails
- configurable Gmail query and maximum thread count;
- strip quoted history where possible;
- cap evidence size before LLM calls;
- hash-based idempotence per thread version;
- no automatic email sending;
- drafts and replies require explicit human approval.

## Deployment dependency
The implementation cannot access a Gmail mailbox until a user-authorized read-only OAuth credential is provisioned in Secret Manager and exposed to the Cloud Run runtime service account.
