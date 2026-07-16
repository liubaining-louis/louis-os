# Codex Engineering Adapter v0.1

## Role and boundary

Louis OS remains the orchestrator. It observes, prioritizes, defines engineering missions, applies safety policy, persists evidence, and decides whether a result stays blocked, requires approval, or may be proposed for promotion.

The engineering agent is a replaceable specialist behind the `EngineeringAgent` protocol. The local `CodexEngineeringAdapter` inspects a repository, produces a constrained plan and patch, runs allowlisted validation commands, and returns structured evidence. It never merges, deploys, changes IAM or billing, sends email, or reads credentials.

Version 0.1 is deliberately local and deterministic. It makes no Codex API call and requires no API key. A future Codex backend must implement the same protocol so Louis OS does not depend on one provider or API.

## Contract

`EngineeringMission` contains `mission_id`, `repository_path`, `allowed_paths`, `objective`, and `dry_run`. Dry-run defaults to `true`.

The operations are:

- `inspect_repository`: read-only Git inspection returning branch, SHA, relevant files, observations, risks and evidence.
- `propose_change_plan`: structured problem, proposed and forbidden files, minimal change, tests, benchmark, risks, stop conditions and approval level. It does not write.
- `generate_patch`: deterministic unified diff. It validates the branch, path allowlist, protected paths, risky actions and secret-like content before writing. In dry-run it never applies the diff.
- `run_tests`: executes only explicitly allowlisted argv sequences through the sandbox and returns exit code, parsed test counts, duration and bounded excerpts.
- `run_benchmark`: executes the real ATLAS command twice, reads `results/summary.json`, verifies reproducibility and blocks promotion on missing evidence, score/pass-rate regression, or critical guardrail regression.
- `summarize_result`: returns a JSON-serializable mission result with files, tests, benchmarks, blockers, evidence and the next action.

Statuses are `completed`, `validation`, `blocked`, `approval_required`, and `failed`. `validation` means local evidence is green; it is not production validation or permission to merge.

## Safety and approval

The adapter rejects direct changes on `main` or `master`, paths outside the mission allowlist, path traversal, protected credential paths, private-key files, secret-like content and destructive actions. Risky external actions return `approval_required`. Secrets found in command output are redacted before logs are returned, and output is truncated to a configured maximum.

No adapter result authorizes a push, PR merge, deployment, email, payment, purchase, IAM/billing change, destructive data access, security bypass, test disabling, benchmark disabling, or quality-threshold weakening. These remain outside v0.1.

## Local sandbox

`LocalCommandSandbox` uses an explicit resolved working directory, argv execution with `shell=False`, a command-prefix allowlist, a timeout, bounded stdout/stderr, a minimal environment allowlist and secret redaction. It never elevates privileges and does not forward provider credentials. The v0.1 local process boundary cannot provide a kernel-level network namespace; commands are therefore limited to the repository's deterministic test and benchmark entry points. A stronger isolated backend can replace it through `CommandRunner`.

Temporary repositories are used by contract tests and cleaned by the test framework. Command results and operations may be persisted through `JsonlEngineeringEvidenceStore`, whose idempotent records are compatible with the existing append-only Evidence Graph and can be ingested into the cycle store later.

## Local verification

Install declared dependencies, then run:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m atlas.cli run-all
python -m atlas.cli report
```

The adapter invokes the interpreter configured by `PYTHON` when one is explicitly supplied. The benchmark must be repeated and its summaries must match before `promotion_allowed` can be true.

## Example configuration

Only variable names are shown; values belong in the runtime secret/configuration system.

```text
PYTHON
ENGINEERING_EVIDENCE_PATH
ENGINEERING_SANDBOX_TIMEOUT_SECONDS
ENGINEERING_SANDBOX_MAX_OUTPUT_CHARS
```

No Codex credential is used by the deterministic backend. A future remote backend may define provider-specific variables in deployment configuration, but must never persist or log their values.

## Future backend and rollback

To activate a real Codex backend later, implement `EngineeringAgent`, keep the same data models and policy gates, inject it into Louis OS, and first validate it in dry-run with external/network access disabled. Promotion requires unit tests, repeated benchmark evidence, CI, explicit human review and a separate production validation record.

Rollback is configuration-first: stop injecting the remote backend and restore `CodexEngineeringAdapter`. To remove v0.1 completely, revert the adapter commit; no database migration, cloud resource or secret cleanup is required because this increment creates none.
