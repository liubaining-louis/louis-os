# Universal Market Execution Plan

This plan operationalizes the permanent mission in `docs/prompts/UNIVERSAL_MARKET_MONETIZATION.md`.

## Phase 1 — Universal discovery fabric

- Normalize opportunities from official APIs, public official pages, allowlisted partner feeds and authenticated platform APIs.
- Keep source-specific compliance metadata and fail closed when credentials, eligibility or terms are unresolved.
- Rank opportunities by verified payability, time to cash, expected value, capability coverage, competition, cost, risk and human dependency.

## Phase 2 — Capability gap loop

- Match every opportunity against a versioned capability registry.
- Mark opportunities as `executable_now`, `prepare_then_gate`, `capability_build`, or `rejected`.
- For `capability_build`, produce an idempotent capability specification with interfaces, tests, budget and the originating opportunity.
- Create at most two internal capability issues per cycle; never create external commitments during capability acquisition.

## Phase 3 — Execution and proof

- Route executable work to the relevant bounded executor.
- Preserve legal, account, identity, payment and KYC gates at the exact external action boundary.
- Record artifacts, hashes, test evidence, submission receipts and payment proof.
- Never infer revenue from acceptance, merge or verbal confirmation alone.

## Initial source coverage

- GitHub bounties through the existing final-safe pipeline.
- Active federal prize challenges through the official USA.gov listing.
- Upwork, Kaggle, HackerOne and SAM.gov as credential-gated official API sources.
- Reviewed JSON partner feeds through the existing allowlisted HTTP source layer.

## Success criteria

- At least one non-GitHub source is scanned in production.
- Source failures do not stop other sources.
- Capability gaps become bounded internal development tasks.
- Opportunities with unresolved terms or identity requirements are prepared but not submitted.
- Every claimed external action and euro of revenue has auditable evidence.
