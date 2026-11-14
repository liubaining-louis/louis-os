# Louis OS v3 — Strategic Brain preparation

## Status

Preparation only. This document defines the target architecture, contracts, evaluation plan and staged delivery gates for Louis OS v3. It does not authorize autonomous production actions.

## Objective

Louis OS v3 must evolve from selecting technically valid work to selecting the most valuable safe action for a durable strategic objective.

The Strategic Brain sits above the existing initiative loop. It does not replace deterministic scoring, evidence requirements, approval gates, benchmarks or provider fallback. It supplies a structured strategic context that those existing components can evaluate.

## Non-goals

- no psychological diagnosis or protected-trait inference;
- no manipulation, coercion or deceptive persuasion;
- no autonomous external e-mail, payment, purchase, IAM, secret, deployment or destructive action;
- no direct merge of risky changes;
- no opaque score that bypasses evidence or deterministic policy.

## Core decision contract

Every strategic recommendation must contain:

- `decision_id`: stable idempotency key;
- `goal_ids`: persistent strategic goals served;
- `evidence_refs`: provenance references supporting the recommendation;
- `candidate_actions`: reversible options considered;
- `expected_value`: normalized benefit estimate with confidence interval;
- `cost`: token, time, monetary and operational estimates;
- `risk`: technical, legal, commercial, reputational and safety dimensions;
- `uncertainties`: explicit missing evidence and assumptions;
- `constraints`: approvals and forbidden action classes;
- `recommended_action`: one selected low-risk action or `no_action`;
- `success_metric`: measurable outcome and evaluation horizon;
- `rollback_plan`: deterministic reversal or containment procedure;
- `status`: `proposed`, `approval_required`, `validation`, `promoted`, `rejected` or `learned`.

## Architecture

### 1. Strategic observer

Builds a minimal evidence bundle from persistent goals, recent cycle records, benchmark trends, failures, PR state, deployment health and approved business signals.

It must fail closed when a required evidence source is missing and must never fabricate connected-data observations.

### 2. Opportunity generator

Produces a small bounded set of candidate actions. Candidates must map to active goals and declare effort, reversibility, expected value, uncertainty and required approvals.

### 3. Strategic evaluator

Evaluates candidates with deterministic policy first and LLM analysis second. The LLM may explain or challenge a score but cannot override hard safety constraints.

Initial dimensions:

- goal alignment;
- expected measurable benefit;
- confidence and evidence quality;
- urgency and opportunity decay;
- implementation effort;
- reversibility;
- operational and reputational risk;
- information gain;
- cost budget.

### 4. Multi-agent council

Use specialist roles only when they add evidence:

- Domain Specialist;
- Risk and Compliance Critic;
- Financial/Cost Analyst;
- Customer Communication Reviewer;
- Technical Feasibility Reviewer;
- Evidence Auditor.

The planner selects the smallest useful subset. Safe evidence gathering may run in parallel. Contradictions must be preserved, not averaged away.

### 5. Decision synthesizer

Returns one action, `approval_required`, or `no_action`. It records dissent, uncertainty, evidence provenance and stop conditions.

### 6. Learning recorder

After the evaluation horizon, compare predicted and observed outcomes. Store calibration error, rejected hypotheses, unexpected effects and reusable lessons in persistent and semantic memory.

## Responsible customer communication layer

Louis OS may assess communication-relevant signals present in the conversation, such as stated priorities, objections, formality, urgency, requested detail and decision stage.

It must not claim to diagnose personality, mental state or vulnerability. It must not infer sensitive traits. Recommendations must remain truthful, respectful, non-coercive and aligned with the customer's expressed needs.

Before an external message can be proposed for approval, the layer should return:

- observed communication signals with quoted evidence references;
- likely customer objective and confidence;
- unresolved objections;
- recommended tone, structure and call to action;
- factual claims requiring verification;
- manipulation and overclaim checks;
- approval status.

## Multi-provider execution policy

The Strategic Brain must reuse `LLM_PROVIDER_ORDER` and the current provider health/cooldown system.

For each analytical step:

1. minimize context to the evidence relevant to the step;
2. call the current eligible provider within its token and cost budget;
3. on quota, cooldown, token-limit or transient failure, record the failure class and continue with the next configured provider;
4. do not substitute one provider inside an independent multi-model comparison that requires distinct outputs;
5. stop only when no configured eligible provider remains or a hard policy gate is reached.

## Delivery stages

### V3.0 — Contracts and deterministic baseline

- typed strategic decision models;
- deterministic candidate scoring;
- evidence and approval contracts;
- unit tests for ordering, idempotence, missing evidence, risk and budgets;
- no external actions.

### V3.1 — Goal-to-decision integration

- connect persistent goals to strategic candidates;
- progress and conflict-aware prioritization;
- prediction and outcome records;
- benchmark against a static decision dataset.

### V3.2 — Dynamic specialist council

- agent registry;
- planner-selected specialist subset;
- parallel read-only evidence gathering;
- contradiction and provenance tracking;
- token/time/cost caps.

### V3.3 — Responsible commercial communication review

- evidence-grounded communication signal extraction;
- objection and tone evaluation;
- factual-claim verification gate;
- anti-manipulation benchmark;
- drafts remain approval-required.

### V3.4 — Production shadow mode

- run beside current decisions without acting;
- compare recommendations to human choices and outcomes;
- calibration, false-positive and opportunity-cost metrics;
- production action remains disabled.

### V3.5 — Controlled promotion

Only reversible low-risk internal actions may be promoted automatically after CI, benchmark and production-shadow evidence are green. External communications and consequential business actions remain approval-required.

## Initial benchmark suites

1. `strategic_selection_v1`: choose the highest-value safe action from evidence-backed candidates.
2. `strategic_abstention_v1`: select `no_action` when evidence is insufficient.
3. `strategic_safety_v1`: route risky or consequential actions to `approval_required`.
4. `strategic_calibration_v1`: compare predicted benefit/confidence with observed outcome.
5. `commercial_communication_v1`: improve clarity and relevance without unsupported claims or manipulative tactics.
6. `provider_resilience_v1`: preserve result contracts across provider failure, cooldown and context reduction.

Promotion metrics must include task success, critical-regression count, abstention precision, unsafe-action recall, evidence coverage, calibration error, latency and estimated cost.

## First implementation slice

Create a low-risk V3.0 pull request containing only:

- `StrategicDecision`, `CandidateAction`, `RiskAssessment` and `DecisionOutcome` models;
- deterministic validation and serialization;
- a baseline scorer that consumes existing strategic goals and action budgets;
- tests proving idempotence, stable ordering, fail-closed evidence behavior and approval routing;
- a versioned benchmark fixture;
- no LLM call and no production integration.

## Promotion gates

A V3 capability is not complete until all are true:

- implementation and tests exist;
- before/after benchmark evidence is recorded;
- no existing ATLAS benchmark regresses;
- documentation and `PROJECT_FOLLOW_UP.md` are updated;
- production shadow evidence exists where applicable;
- rollback is documented;
- approval boundaries are tested;
- the result is stored as an experiment.

## Immediate next step

After the current strategic-goal initiative bridge is resolved, implement V3.0 contracts and the deterministic baseline on a dedicated branch. This preserves the one-major-capability-at-a-time execution policy while making the next engineering slice explicit and testable.
