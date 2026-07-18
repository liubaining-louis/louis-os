# Autonomous Venture Cycle

`AutonomousVentureCycle` closes one bounded AVB learning loop:

1. rank evidence-backed opportunities;
2. select one opportunity through the deterministic CEO policy;
3. create a decision artifact and a validation experiment;
4. stop before any unapproved external action;
5. record a measurable observation;
6. compare the candidate with the mission #47 baseline;
7. promote only when every guardrail passes;
8. append the decision, assets and result to auditable JSONL memory.

## Promotion gates

A candidate is not promoted when any of these conditions is true:

- the experiment does not reach its success threshold;
- its decision score is below the mission #47 baseline;
- its autonomy score is below the mission #47 baseline;
- unsupported claims increase;
- no measurable observation exists;
- an external action lacks explicit approval.

## Artifacts

Each cycle writes deterministic, reviewable files:

- `decision.json`;
- `experiment.json`;
- `result.json`;
- `venture-memory.jsonl`.

The runtime performs no network calls, spending, publication, email delivery or commercial commitment. Those actions remain blocked unless approval is explicitly represented by the caller.
