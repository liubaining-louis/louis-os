# Workflow cycle policy

Louis OS uses event-driven or manual execution by default. Scheduled execution is reserved for work whose source can change without a GitHub event.

## Scheduled lanes

| Workflow | Cadence | Purpose |
| --- | ---: | --- |
| Universal market monetization | Twice daily | Discover and rank newly available payable work |
| External outcome reconciliation | Every 6 hours | Verify acceptance, queued payouts and wallet settlement |
| Monitor Taskmarket claims | Daily | Detect claim, selection or payout state changes |

All other operational workflows remain available through relevant file changes, GitHub events, or manual dispatch.

## Guardrails

- Maximum 3 scheduled workflows.
- Maximum 7 scheduled starts per day.
- No scheduled interval below 60 minutes.
- Every scheduled workflow keeps manual dispatch and cancels an obsolete overlapping run.
- State monitors publish and commit only meaningful transitions.
- CI on pushes ignores results-only and documentation-only ledger churn while pull requests still receive the full required CI.
