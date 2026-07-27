# Decision — Truelancer public cash-first source

## Status

Accepted as a read-only discovery source for the issue #77 cash-first lane.

## Purpose

The Truelancer adapter diversifies simple-mission discovery beyond Freelancer.com and Guru. It targets current remote digital work with public budget and competition evidence while preserving platform payment safety.

## Authoritative public evidence

The adapter may use only official public pages on `www.truelancer.com` and records:

- canonical public project URL;
- fixed budget or hourly rate;
- estimated hours when hourly;
- public proposal count;
- posting age;
- active detail-page status;
- client projects paid and total spent when displayed;
- the platform warning to never pay a security deposit and keep transactions on-platform.

A generic title, promotional text, average freelancer quote or amount copied from a third-party page is not payment evidence.

## Cash-first acceptance policy

A project is eligible for further routing only when all of the following hold:

- it is recent and active;
- a positive explicit budget is displayed;
- estimated effort does not exceed 16 hours;
- proposal count remains within the configured competition ceiling;
- the scope is remotely deliverable and bounded;
- the required capability maps to an allowed digital-delivery family;
- the client has at least one paid project or positive public spend evidence;
- the description does not prohibit AI, automation or the authorized delivery method;
- no physical presence, sensitive verification, deceptive activity, off-platform payment or prohibited work is required.

Failure or ambiguity in any mandatory signal causes rejection or omission. It must not create a human gate or a capability gap.

## Payment and safety

All prospective payment remains on Truelancer. Louis OS must never:

- pay a security deposit or registration fee;
- move payment to WhatsApp, Telegram, direct crypto or another off-platform channel;
- begin work without the platform's applicable payment protection;
- record a proposal, award, contract or revenue without a platform receipt.

The payment method recorded before award is therefore: Truelancer platform payment, with the account payout method selected only if and when an actual award requires it.

## Proposal preparation and human gate

Read-only discovery, evidence verification, mission clustering and proposal-dossier preparation are reversible internal actions.

When a qualifying mission reaches `prepare_then_gate`, Louis OS prepares:

- conservative quote and effort;
- client-facing proposal;
- deliverable and validation checklist;
- payment, competition and scope evidence;
- proposal manifest and artifact hash.

Only then may it request the minimum human action:

> Authorize use of a truthful Truelancer account and review/accept the platform terms so Louis OS can submit the prepared proposal. Keep all payment on-platform; never pay a security deposit.

KYC, tax or payout configuration remains deferred until Truelancer explicitly requires it for a real account or award.

## Source-of-truth outputs

The adapter contributes to:

- `results/simple_mission_source_refresh.json`;
- `results/universal_market_opportunities.json`;
- `results/capability_market.json`;
- `results/mission_clusters.json`;
- `results/cash_first_market.json`;
- `results/human_action_required.json`;
- `results/monetization.json`;
- issue #77.

No source artifact can independently increment receipt-backed submission, conversion or revenue counters.
