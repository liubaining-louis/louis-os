# Controlled Self-Evolution

Louis OS may improve itself, but it may not promote unverified changes.

## Permanent loop

1. Detect the largest measured bottleneck.
2. Propose one bounded hypothesis.
3. Implement the smallest reversible change.
4. Run tests and deterministic evaluators.
5. Compare candidate metrics with the baseline.
6. Promote only when there is no guarded regression and the gain exceeds the configured threshold.
7. Otherwise hold or roll back, then record the lesson.

## Safety boundaries

- No irreversible autonomous self-modification.
- No automatic promotion of high-risk changes.
- No promotion without measurable evidence.
- Any regression in a guarded metric blocks promotion.
- Revenue improvement never overrides legality, reliability, evidence quality, or explicit owner controls.

## North Star

Increase verified autonomous revenue while preserving safety, reliability, and auditable evidence.

## Initial implementation

`atlas/evolution.py` provides:

- typed evolution proposals;
- measurable evaluation signals;
- weighted candidate-versus-baseline comparison;
- deterministic promote, hold, or rollback decisions;
- explicit controls for reversibility and high-risk changes.

This module is the decision kernel. Future automation may create branches and pull requests around it, but branch protection and CI remain the final promotion gate.
