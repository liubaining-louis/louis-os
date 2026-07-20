# Louis OS — Project Follow-up

This file records evidence-backed status against `docs/IMPROVEMENT_BACKLOG.md`. A green local run is not production validation.

## Louis OS ↔ Codex mentor MCP bridge

- Problem: the OpenAI Platform connector was unavailable in the user's Codex environment, so an OpenAI API key could not be provisioned safely through the approved flow.
- Alternative: Louis OS exposes a Streamable HTTP MCP endpoint backed by its existing Firestore chat and multi-model router; no OpenAI API key is required.
- Isolation: each pairing creates a server-generated dedicated chat session, stores only a token digest, expires after a bounded TTL and cannot select another session.
- Tools: paired history, message to Louis OS, pending mentor requests and idempotent Codex reply.
- Safety: anonymous MCP calls fail with 401, unapproved origins fail with 403, token values are never persisted in Git or Firestore, and tools expose no deployment, IAM, payment, email or merge action.
- Status: `in_progress`; promotion to `validation` requires the complete local suite, ATLAS benchmark, green CI, successful Cloud Run smoke tests and a real Codex MCP connection.

## Secure autonomous runtime v1

- Production audit finding: the public dashboard issued a valid authenticated session to anonymous visitors, exposing protected reads and, by contract, protected write routes.
- Reliability finding: the autonomous monetization workflow repeatedly failed during final Firestore synchronization before committing its evidence ledger.
- Corrective increment: explicit API-key-to-session exchange, anonymous 401 enforcement, deployment security probes, Workload Identity authentication, failure-isolated evidence persistence and truthful executable/gated candidate projection.
- Governance improvement: a high/critical remediation with new evidence can pass the maturity gate without increasing a score; domain regressions remain forbidden.
- Local validation: `338/338` unit tests passed; ATLAS guarded score `0.9444444444444445`, pass rate `0.8333333333333334`, critical regressions `0`; maturity history promoted both remediations with no score change.
- Scores: unchanged pending production evidence. This is a remediated critical finding, not a claim of greater proven autonomy.
- Status: `validation`; promotion requires green CI, successful deployment security probes and one successful scheduled monetization cycle with Firestore synchronization.

## Permanent mentor maturity cycle v1

- Baseline revision: `31c8a96a22109fdff3b9f10e267a7e1ddcde0ff8`.
- Identified gap: no versioned maturity assessment and no CI rule preventing maturity regression across pull requests.
- Increment: typed scorecard loader, deterministic comparison gate, versioned baseline/candidate assessments, eight targeted tests and mandatory CI scorecard validation; evidence paths and evidence-strength transitions fail closed.
- Measured change: robustness `8 -> 9`; overall maturity `7.29 -> 7.43`; every other domain unchanged; no maturity regression.
- Primary remaining weakness: results `4/10`, because receipts exist but repeated externally verified economic outcomes do not.
- Status: `validation`; production maturity must not be inferred from local or CI evidence.

## Results weakness cycle v1 — execution readiness

- Observed failure: the highest-ranked opportunity advertised a USD 750 reward but required third-party sign-up, a formal claim and maintainer confirmation before work could begin. It was nevertheless marked `qualified_and_prepared` and became the execution candidate.
- Root cause: attractiveness and execution readiness shared one ranking. Reward size could outweigh prerequisites that Louis OS was not authorized or able to satisfy autonomously.
- Increment: deterministic prerequisite detection, separate `execution_score`, fail-closed readiness metadata, executable-only candidate selection and a second refusal in the external action executor.
- Test integrity: previously function-style external-action tests were invisible to the repository's `unittest` command. They are now `unittest.TestCase` suites and increase the executed suite from 311 to 324 tests.
- Real replay: the ten stored candidates are now refused as non-executable because their historical artifacts contain no cleared readiness evidence; the prepared external action remains unsubmitted.
- Benchmark: ATLAS guarded score `0.9444444444444445`, pass rate `0.8333333333333334`, critical regressions `0`; unchanged from the prior candidate.
- Maturity impact: results remains `4/10`. Selection quality improved, but no response, accepted submission, order or revenue receipt exists yet.
- Status: `validation`; the next proof must be one executable opportunity advanced to an externally verified response without weakening approval, identity or financial gates.

| Roadmap item | Status | Evidence | Remaining gate |
|---|---|---|---|
| 1. Autonomous initiative loop | `validation` | Scoring, action budgets, approval gates, the deterministic Observe → Prioritize → Plan → Simulate → Evaluate → Learn cycle and the injected Firestore cycle-store adapter are on `main`. Branch `feature/strategic-goal-initiative-bridge-v2` connects durable goals to opportunity selection. PR #45 adds a deterministic strategic decision contract and executable selection benchmark; ATLAS CI run #123 passed on commit `9d33df441366c7cd49e3077f6e5a9c381be4126c`. | Require approved production Firestore wiring, real repository/deployment observations and a production validation record. |
| 2. Semantic memory | `validation` | Deterministic local semantic retrieval, lexical fallback and retrieval benchmark gates were merged through PRs #37 and #40. | Validate against production memories and add managed-provider/vector-index support before `completed`. |
| 3. Advanced multi-agent orchestration | `in_progress` | Sequential Planner → Specialist → Critic → Revision → Synthesizer is on `main`. | Dynamic selection, parallel safe evidence, consensus and budgets remain. |
| 4. Self-modification workflow | `validation` | Codex Engineering Adapter v0.1 contract, deterministic local adapter, sandbox, security policy, 17 contract tests, a green dry-run demo and green PR CI were merged through PR #31. | Production validation remains. No autonomous risky merge is authorized. |
| 5. Persistent strategic goals | `validation` | Persistent goal records, idempotent JSONL audit history, progress, reprioritization, conflict detection and abandonment reasons were merged through PR #34; branch `feature/strategic-goal-initiative-bridge-v2` adds deterministic conversion into initiative opportunities. | Require green CI for the bridge and production persistence validation before `completed`. |

## Strategic selection benchmark v1

- Hypothesis: a versioned executable dataset can prevent changes to strategic scoring, evidence gates, approval routing or budgets from being promoted when expected decisions change.
- Dataset: four deterministic cases covering highest-safe-value selection, missing-evidence abstention, high-risk approval routing and cost-budget refusal.
- Evaluator: `atlas.strategic_benchmark.evaluate_strategic_selection_benchmark` reconstructs typed candidates, executes the production selector and compares status plus selected action.
- Promotion gate: every case must pass; malformed or empty datasets fail closed, and a mismatched expected decision returns `passed=false`.
- Tests: reference fixture success, deliberate expectation mismatch and invalid empty dataset.
- Safety: deterministic local evaluation only; no LLM, provider, network, secret, IAM, deployment, payment, e-mail, purchase or destructive action.
- Validation status: validated in ATLAS CI run #123 on commit `9d33df441366c7cd49e3077f6e5a9c381be4126c`; PR #45 remains unmerged pending review and the autonomous initiative loop remains `validation` until production observations and persistence are approved.

## Strategic goal → initiative bridge v2

- Hypothesis: converting active, incomplete strategic goals into the existing deterministic `Opportunity` model lets the initiative cycle select work from durable objectives without adding a second prioritization system.
- Mapping: normalized priority becomes impact and remaining metric gap becomes urgency; explicit effort and risk continue to be enforced by `ActionBudget`.
- Lifecycle: paused, completed, abandoned and already-at-target goals produce no autonomous opportunity.
- Determinism: converted opportunities are sorted by goal id and final selection retains the existing score and tie-break contract.
- Tests: high-gap selection, inactive/at-target filtering, order independence and invalid resource inputs.
- Safety: local deterministic transformation only; no provider, secret, IAM, deployment, payment, e-mail, purchase or destructive action.
- Validation status: implementation is on `feature/strategic-goal-initiative-bridge-v2`; promotion requires green full CI and unchanged ATLAS benchmarks.

## Firestore initiative-cycle persistence v1

- Hypothesis: an injected Firestore collection using atomic document creation can preserve autonomous cycle records across instances without duplicating execution or hiding cloud failures.
- Contract: `CycleStore` decouples the runner from local JSONL and cloud persistence implementations.
- Idempotence: cycle fingerprints are Firestore document identifiers; an existing record is returned before execution, and a concurrent create race returns the immutable winning record.
- Failure behavior: unrelated Firestore errors are re-raised rather than being reported as successful persistence.
- Credential boundary: the core module does not import or initialize Firestore credentials; an approved runtime bootstrap must inject the collection.
- Tests: Firestore round-trip, duplicate handling and non-duplicate error propagation, in addition to the existing lifecycle, regression, approval and missing-evidence tests.
- Validation status: implementation was merged through PR #42 after green CI. Production wiring remains approval-required because it touches cloud identity and deployment configuration.

## Autonomous initiative dry-run cycle v1

- Hypothesis: a deterministic, idempotent cycle runner can prove the complete initiative lifecycle before any autonomous production action is allowed.
- Flow: Observe → Prioritize → Plan → Simulate → Evaluate → Learn.
- Promotion gate: simulation must provide explicit evidence, pass validation and report no regression; otherwise the hypothesis is stored as rejected.
- Safety gate: opportunities requiring approval or exceeding the action budget are never planned or simulated and become `approval_required` or `no_action`.
- Persistence: append-only JSONL records keyed by an order-independent cycle fingerprint; duplicate executions return the original record without invoking the planner or simulator again.
- Tests: complete path/idempotence, regression refusal, unsafe approval routing and missing-evidence fail-closed behavior.
- Validation status: implementation was merged through PR #41 after green CI; Firestore production persistence and real observations remain separate gates.

## Semantic memory retrieval benchmark v1

- Hypothesis: a versioned retrieval dataset with explicit hit-rate@3 and mean reciprocal rank gates prevents semantic-memory changes from being promoted without demonstrated retrieval quality.
- Dataset: three domain-filtered queries across charcoal and engineering memories, with unrelated distractors and stable expected memory identifiers.
- Metrics: hit-rate@3 and mean reciprocal rank; the reference gates require `1.0` hit-rate@3 and at least `0.8` MRR.
- Failure behavior: missing cases/memories raise an error, and unmet thresholds return `passed=false` to block promotion.
- Safety: deterministic local execution only; no network, provider credentials, secrets, IAM, deployment, e-mail or paid API calls.
- Validation status: implementation and targeted tests were merged through PR #40 after green CI.

## Persistent strategic goals v1

- Hypothesis: an append-only strategic-goal store plus deterministic progress and priority functions gives the initiative loop durable objectives without introducing cloud, IAM or secret risk.
- Data contract: goal id, title, owner, metric, target, current value, horizon, priority, direction, lifecycle status, update timestamp and abandoned-hypothesis reason.
- Lifecycle: upsert, progress update, automatic completion at target and explicit abandonment with mandatory audit reason.
- Decision support: normalized progress, gap-weighted priority score, deterministic reprioritization and same-metric direction conflict detection.
- Persistence: dependency-free JSONL event log suitable for local tests and dry-run operation; production Firestore integration remains a later validation gate.
- Safety: no external calls, secrets, IAM, deployment, payments, e-mails or destructive actions.
- Validation status: targeted tests and idempotence coverage passed in GitHub CI before merge through PR #34.

## Codex Engineering Adapter v0.1 validation record

- Base SHA: `25e5d13013cc629fda642b7777e712a6db14d3bc`.
- Baseline before implementation: 59 unit tests passed after installing declared dependencies.
- Baseline ATLAS: baseline score `0.4444444444444444`, guarded score `0.9444444444444445`; pass rates `0.3333333333333333` and `0.8333333333333334`; guarded critical regressions `0`.
- Contract coverage: read-only inspection, default dry-run, allowlist, main/secret/destructive refusal, failed commands, benchmark regression and promotion blocking, structured output, idempotence, log truncation/redaction, and approval-required routing.
- Post-implementation suite: 76 tests passed with `python -m unittest discover -s tests -v`.
- ATLAS benchmark was executed twice by the adapter and produced identical summaries: score delta `+0.5000000000000001`, pass-rate delta `+0.5`, no guarded critical regression, complete evidence and no detected regression.
- `python -m atlas.cli report` generated `results/report.html` successfully.
- Demo mission `codex-demo-001`: inspection and plan completed; one documentation patch was generated in dry-run and was not applied; tests and benchmark passed; structured summary status `validation`; no approval was required.
- GitHub `ATLAS CI` run #83 passed for commit `4b111b141bb773b0a28cfeee8acb453e1fd5a70e` in draft PR #31.
- Status is `validation`, not `completed`: human review and real production validation are still required.

## Multi-model comparison harness

- Implementation status: `validation`; 9 targeted tests cover same-prompt execution, provenance, deterministic coverage, discrepancies, provider isolation, failure blocking and secret redaction.
- Live mission status: `blocked`; `coal-email-multimodel-001` found neither Groq credentials nor a Vertex project/workload identity in the local runtime.
- Full validation: 85 tests passed; ATLAS benchmark and report remained green with no score or guardrail regression.
- Scope: explicit same-prompt comparison across Groq and Vertex with separate provenance, deterministic axis coverage, discrepancy reporting and no fallback substitution.
- Safety: no mailbox write, no secret persistence, no deployment and no paid call in unit tests.
- Next gate: configure both provider identities in an approved runtime, then rerun the recorded mission and review the two outputs before any promotion.
