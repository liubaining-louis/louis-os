# Louis OS — Improvement Backlog

This backlog is the execution order for autonomous improvement. Each item must be implemented on a dedicated branch, covered by tests, compared against the previous state, and merged only after CI passes.

## 1. Autonomous initiative loop

Goal: Louis OS no longer waits exclusively for a user command. It observes its own state, selects one low-risk improvement, plans it, executes a reversible step, evaluates the result, and records the outcome.

Required capabilities:
- persistent goals and priorities;
- observation of missions, failures, benchmarks, pull requests and recent deployments;
- deterministic opportunity scoring;
- explicit action budget;
- stop conditions on uncertainty, regression or missing approval;
- cycle records in Firestore;
- dry-run mode by default;
- no autonomous secrets, IAM, payment, email, purchase or destructive actions.

Acceptance criteria:
- one full dry-run cycle produces Observe → Prioritize → Plan → Execute/Simulate → Evaluate → Learn;
- duplicate cycles are idempotent;
- unsafe proposals become approval_required;
- regression prevents promotion;
- tests cover scoring, budgets, stop conditions and persistence.

## 2. Semantic memory

Goal: complement Firestore keyword memory with embeddings and semantic retrieval.

Required capabilities:
- embedding provider abstraction;
- vector index with metadata filters;
- hybrid lexical + semantic ranking;
- deduplication, decay and confidence calibration;
- retrieval evaluation dataset and benchmark.

## 3. Advanced multi-agent orchestration

Goal: move from a mostly sequential chain to dynamic specialist selection and parallel evidence gathering.

Required capabilities:
- agent registry;
- planner-selected agents;
- parallel safe subtasks;
- consensus and contradiction detection;
- explicit provenance per contribution;
- token/time/cost budgets.

## 4. Self-modification workflow

Goal: allow Louis OS to identify a code weakness, create a branch, modify code, run tests, open a pull request and evaluate the change.

Required capabilities:
- repository inspection agent;
- constrained file-editing plan;
- branch and PR lifecycle;
- CI result ingestion;
- benchmark before/after comparison;
- automatic rollback or PR rejection on regression;
- no direct autonomous merge for risky changes.

## 5. Persistent strategic goals

Goal: maintain durable objectives such as reliability, user time saved, business opportunity quality, cost control and memory quality.

Required capabilities:
- goal records with owner, metric, target and horizon;
- decomposition into initiatives and tasks;
- progress measurement;
- conflict resolution between goals;
- periodic reprioritization;
- audit trail of abandoned hypotheses.

## Execution policy

Louis OS must implement these items in order unless a critical defect blocks progress. Only one major capability is active at a time. Every completed item must include code, tests, documentation, benchmark evidence and a production validation record.
