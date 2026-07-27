# Decision — Capability Market Engine

## Status

Accepted for the cash-first monetization loop governed by issue #77.

## Problem

Opportunity-by-opportunity routing causes three structural errors:

1. repeated missions are treated as unrelated work;
2. capability investment can be driven by a large headline prize rather than the probability of the first verified payment;
3. revenue forecasts can be confused with pipeline or realized income.

The capability market engine converts the current qualified market into reusable mission clusters and bounded skill-acquisition plans.

## Decision

### Mission clustering

Qualified opportunities are grouped deterministically by:

- cash-first or strategic lane;
- required capability;
- deliverable family;
- payment horizon and scope signals already captured by the market record.

A cluster keeps its opportunity IDs, independent source count, value by original currency, median effort, median payment delay, competition, accessibility and the best canonical opportunity evidence.

### Capability market score

The score prioritizes:

- cash-first eligibility;
- number of currently observed missions unlocked;
- first-payment probability signal;
- speed to payment;
- small median scope;
- reusable-deliverable ratio;
- independent source diversity;
- implementation cost derived from the validated capability registry.

Headline rewards are capped for scoring. Strategic prizes cannot dominate a smaller reusable capability simply because the advertised prize is large.

Currencies are never silently converted or summed together. Verified market value is retained by currency.

### Capability build plan

A nonvalidated capability may be promoted to a build plan only when a cash-first cluster supports it. Every plan includes:

- a bounded input/output interface;
- originating opportunity fixtures;
- unit and dry-run acceptance tests;
- artifact hashing and evidence requirements;
- a promotion rule;
- a stop rule;
- a budget rule;
- immediate market requalification after promotion.

A capability is deferred when no qualifying mission remains for three consecutive cycles, its market score falls below the stop threshold, or mandatory human/physical constraints dominate.

### Incompatible method requests

A payer's explicit prohibition of AI, automation or the authorized delivery method is a policy rejection, not a capability gap. Such opportunities must be marked `rejected` before proposal preparation, human gating or capability investment.

### Reusable proposal templates

The engine may prepare one internal proposal template for every cash-first cluster. A template is reusable preparation evidence only. It is not a submitted proposal, agreement, contract or platform receipt.

### Revenue simulation

Simulations are computed only from currently observed qualified opportunities and remain separated by currency. Conservative, base and upside expected values are planning signals.

Every simulation must state:

- `type = simulation_only`;
- `counted_as_pipeline = false`;
- `counted_as_revenue = false`;
- annualization is unavailable until sufficient observed history exists.

Simulation values must never modify submission, conversion or verified-revenue counters.

## Source of truth and evidence

The engine writes:

- `results/capability_market.json`;
- `results/mission_clusters.json`;
- `results/capability_build_plan.json`;
- `results/revenue_simulation.json`;
- `results/capability_market_history.json`;
- `results/cluster_proposal_templates/`;
- enriched `results/capability_backlog.json`;
- synchronized planning fields in `results/monetization.json`.

Issue #77 remains the master operational dossier. External submission and revenue truth continue to require independent platform or payment receipts.

## Human gates

Clustering, scoring, simulation, testing and proposal-template preparation are reversible internal actions. They require no human validation.

A human action is requested only after a concrete mission has a complete dossier and the exact account, terms, identity, signature, KYC or payout gate is reached. No simulated market value justifies an early gate.
