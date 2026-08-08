# Louis OS — Time & Capacity Policy

Louis OS treats time and compute as scarce productive resources.

## Operating principle

A production worker must be work-conserving: while there is safe, useful work inside the autonomy envelope and remaining cycle budget, it should not intentionally idle.

Priority order:
1. Execute currently payable / submission-ready work.
2. Build or validate current deliverables.
3. Refresh/expand market access when the pipeline is sparse.
4. Recover candidate state and remove structural blockers.
5. Run quality/review/calibration work.
6. Use residual capacity for learning, diagnostics, capability preparation and other reversible GREEN improvement work.

## Cycle accounting

Every worker cycle records:
- cycle budget seconds;
- active work seconds;
- remaining seconds;
- actions completed;
- utilization percent;
- reason for any unused capacity;
- last chosen autonomous action.

A cycle should keep taking the next autonomous action until the remaining budget is below the reserve required for state synchronization, a genuine external gate is reached, or a bounded safety/rate-limit condition requires backoff.

## Anti-busywork rule

`100% utilization` is not a goal by itself. Repeating ineffective API scans or model calls simply to consume compute is prohibited. If an action repeatedly produces no measurable progress it should be demoted, and residual capacity should move to a different reversible task family such as diagnosis, learning, source expansion, capability preparation or tests.

## Engineering KPI

The target is productive utilization, not raw CPU burn:

`productive_utilization = useful_action_time / available_cycle_time`

This metric must be interpreted together with economic leading indicators and realized payout. A high-utilization worker with no pipeline progress must autonomously change strategy.
