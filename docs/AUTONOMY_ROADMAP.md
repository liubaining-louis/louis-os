# Louis OS autonomy roadmap

## Target interaction

User -> ChatGPT -> GitHub command gateway -> Louis Core -> planner -> memory retrieval -> execution -> evaluation -> Firestore -> result.

## Milestone A — Louis Core v0.5

- Deterministic mission classification.
- Structured plans with explicit risk levels.
- Human approval gate for external or irreversible actions.
- Plan validation and unit tests.

## Milestone B — Persistent memory v0.6

- Firestore collections: `memories`, `mission_steps`, `commands`.
- Memory types: fact, preference, decision, procedure, outcome.
- Provenance, confidence, timestamps and lifecycle state.
- Retrieval by domain, tags and lexical relevance.
- No secret or credential values stored in memory.

## Milestone C — Command bridge v0.7

- A protected `/commands` API.
- GitHub issue or workflow bridge so ChatGPT can transmit a user order without Cloud Shell.
- Command states: received, planned, approval_required, running, completed, failed.
- Idempotency key to prevent duplicate execution.
- Every command links to its plan, mission, evidence and result.

## Milestone D — Autonomous scheduler v0.8

- Cloud Scheduler triggers a safe autonomous cycle.
- Select one queued or self-generated low-risk mission.
- Enforce time, token and cost budgets.
- Stop on uncertainty, policy violation or regression.
- Human approval remains mandatory for external communication, payments, purchases, deletion, publishing and permission changes.

## Definition of done

Louis OS is considered operationally autonomous when it can receive an order, retrieve relevant memory, produce a validated plan, execute permitted steps, persist evidence, report its result and resume after restart without manual Cloud Shell intervention.
