# Connected Intelligence Evolution Plan

## Objective
Make Louis OS capable of analysing connected user data without fabricating records, then progressively operate with semantic memory, a native read-only Gmail connector, and a guarded autonomous loop.

## Delivery order

1. Evidence-grounded command execution — completed in PR #32.
2. Semantic memory retrieval with deterministic fallback and provider abstraction.
3. Native Gmail read-only connector using OAuth/service credentials supplied through Secret Manager.
4. Autonomous inbox loop: fetch, classify, analyse, persist evidence and propose actions.
5. External write actions remain approval-gated: sending, deleting, purchasing, payments and credential changes.

## Acceptance criteria

- Connected-data missions without evidence are blocked before any LLM call.
- Semantic retrieval returns ranked memories with stable deterministic tests.
- Gmail connector stores no message body in logs and never persists access tokens in repository files.
- Autonomous inbox cycles are idempotent and do not send messages automatically.
- Every generated factual claim can be traced to an evidence reference.
