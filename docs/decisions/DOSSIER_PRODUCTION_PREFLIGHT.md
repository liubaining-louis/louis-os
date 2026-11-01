# Production preflight before proposal preparation

## Measured defect — 1 November 2026

At main `76368c979fa97d0189d93abc88d48ffdc213c37b`, market run
41230406499 prepared one proposal for Freelancer listing
`market-45c0d728fc509a87` (Modernise Kernow Roast Co. Website).
The persisted receipt records 12 hours while production permits at most 3.
The final router correctly declined execution with
`effort_exceeds_production_limit`; no bid was submitted. The scope classifier's
acceptance is not a customer acceptance, qualified mission or revenue.

The preparer trusted upstream `prepare_then_gate` before the final cash/router
checks. It created files and an account/terms instruction for work already
outside the production budget. This is unnecessary preparation, not proof of
lost money or a new external-action bypass.

## Bounded change

Load the existing canonical production policy before touching dossier output.
Evaluate each otherwise preparable freelance candidate using the metadata effort
actually consumed by its proposal. Existing reward, blocked-term and global
guards also apply. Missing effort stays explicitly unknown rather than allowing
the proposal builder's eight-hour default to create an actionable dossier.

Blocked candidates keep a diagnostic and dated receipt entry, not proposal paths
or human-action instructions. Existing output cleanup remains unchanged; only
generated, unsubmitted local proposals are managed here, never external receipts.
Prepared counts and next action reflect the gated result. Pure proposal rendering
remains available for tests and is not itself authorization.

No policy values, schedules, source credentials, wallets or submission drivers
change. This does not implement broad WordPress scope analysis, fix the source
pivot, prove platform access or create a payable delivery.

## Verification and rollback

Before the fix, the real 12-hour fixture and reward/kill-switch assertions failed;
invalid effort raised inside proposal rendering. Integration tests now run the
script in an isolated temporary workspace, checking blocked output, stale metadata
cleanup, explicit unknown effort, and a permitted 3-hour boundary. Existing
proposal, production-policy, software and final-router regressions remain required.

Rollback: revert this three-file PR. The downstream router remains an independent
gate. Next existing market cycle must confirm that over-budget input yields a
blocked preparation receipt and zero proposal/account request; if the listing
disappears, do not claim live confirmation. No additional source scan is needed.

Economic effect established locally: one over-budget proposal avoided in replay.
No verified payment, customer delivery, measured monetary saving or guaranteed
income follows from this correction. Actions cost and total operating cost remain
unknown.
