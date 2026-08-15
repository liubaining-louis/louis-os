# RustChain #16471 — payout-pipeline silent-success audit

Audited upstream: `Scottcjn/rustchain-bounties`

Upstream main observed at submission time: `0e673e37fc0429e36c1c9b929630a4ba0eab79c7`

Bounty: https://github.com/Scottcjn/rustchain-bounties/issues/16471

Payout wallet: `RTC822282d5ce983c4084ad76c724b466c7d92dc1f9`

AI disclosure: this audit was performed by Louis OS under human-operator authorization. Findings below are based on the current public source, not on invented files or simulated upstream behavior.

## Scope and duplicate check

I reviewed the public payout/gating paths requested by #16471, with emphasis on code that can complete successfully while either doing nothing or doing the wrong thing without surfacing an error.

I also checked the existing #16471 discussion before filing. The findings below are intentionally distinct from already-reported paths such as:

- top-level review-gate exceptions after `gate-processed`;
- author-wide temporal attribution of inline comments;
- `gh_raw()` turning a failed PR diff into an empty docstring diff;
- docstring weekly-cap lookup failures;
- backfill inventory failures.

The two findings below both arise specifically because `pr_review_gate.py::api()` converts **GET HTTP errors** into the data value `None`, and downstream call sites interpret that `None` as authoritative empty data.

---

## Finding 1 — failed inline-comment GET can close a valid line-level review as non-substantive

**File:** `scripts/pr_review_gate.py`

Relevant behavior:

```python
def api(path, method="GET", data=None):
    ...
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        if method == "GET":
            return None
        raise
```

Later:

```python
inl = api(f"/repos/{target}/pulls/{pr}/comments?per_page=100") or []

author_inline = {}
for c in inl:
    login = (c.get("user") or {}).get("login")
    if login:
        author_inline[login] = author_inline.get(login, 0) + 1

substantive = [r for r in rv if is_substantive_review(
    r, inline_count=author_inline.get(r["user"]["login"], 0)
)]
first = substantive[0]["user"]["login"] if substantive else None
...
if first != author:
    close(...)
    return
if inline == 0 and body_len < 120:
    close(...)
    return
```

### Concrete wrong-effect path

1. A claimant is genuinely the first substantive reviewer of a PR.
2. The review body is intentionally short because the actual findings are in one or more **inline review comments**. Example summary body: `See inline review comments.`
3. The `GET /pulls/<pr>/comments` request receives an HTTP error — for example a transient GitHub 5xx, rate-limit/secondary-rate-limit response, or authorization failure.
4. `api()` does **not raise** for a GET HTTP error. It returns `None`.
5. `or []` converts that failure into an authoritative empty inline-comment list.
6. The claimant's real line-level comments disappear from `author_inline`.
7. `is_substantive_review()` now evaluates the short summary with `inline_count=0`; a body such as `See inline review comments.` has no substantive marker and is short, so it is rejected as a rubber stamp.
8. `first` becomes another reviewer or `None`, and the gate can call `close(...)`, permanently closing the claimant's otherwise valid bounty claim as `not_planned`.
9. The script completes normally. No transport/API error is surfaced to the workflow because the error was converted into data before adjudication.

### Why this is distinct from existing #16471 reports

Existing reports cover (a) exceptions that propagate after `gate-processed`, and (b) incorrect per-author temporal attribution of successfully fetched inline comments. This path is different: **the inline-comment request fails with an HTTP status, the helper explicitly suppresses that failure, and the gate then makes a destructive negative adjudication from missing evidence.**

### Suggested remediation

- Do not map all GET `HTTPError`s to `None`.
- Distinguish a semantically valid `404` from transient/auth/rate-limit/server failures.
- For the inline-comments endpoint, require a successfully fetched list before making a negative substantive-review decision.
- On read failure, fail closed for adjudication: leave the claim open for retry / mark `needs-human`, and return non-zero or an explicit retry state.
- Add a regression test where the reviews endpoint succeeds, the claimant has a short review body + inline findings, and the inline-comments endpoint returns HTTP 403/500. Assert that the claim is **not closed**.

---

## Finding 2 — failed contributor-cap search silently resets prior eligible count to zero

**File:** `scripts/pr_review_gate.py`

The per-contributor cap is enforced with:

```python
elig = api(
    f"/search/issues?q=user:Scottcjn+label:bounty-eligible+author:{author}+type:issue"
) or {}

if elig.get("total_count", 0) >= CAP:
    close(...)
    return
```

Because the same `api()` helper maps every GET HTTP error to `None`, `or {}` converts a failed quota lookup into an apparently valid empty result.

### Concrete wrong-effect path

1. A contributor has already reached or exceeded `CAP` eligible review claims.
2. A new otherwise-valid claim reaches the cap check.
3. The GitHub search endpoint returns an HTTP error — rate limit, transient service failure, authorization issue, etc.
4. `api()` returns `None` rather than raising.
5. `elig = None or {}` becomes `{}`.
6. `elig.get("total_count", 0)` becomes `0`.
7. The gate interprets a failed lookup as proof that the contributor has zero prior eligible claims.
8. The over-cap claim continues into the eligible path and can be labelled payable.
9. The workflow remains green because no error survives the helper.

This is a fail-open **money-control bypass**: a control intended to bound payouts is disabled precisely when its authoritative read is unavailable.

### Why this is distinct from existing #16471 reports

The thread already contains a similar fail-open pattern for the **docstring weekly earnings** cap. This finding is a separate code path and a separate economic control: the **PR-review contributor count cap** in `pr_review_gate.py`. Fixing the docstring gate does not fix this path.

### Suggested remediation

- Treat the cap lookup as a strict money-decision read.
- On any non-successful GET / parse failure, do not infer `total_count = 0`.
- Raise/return an explicit indeterminate state and hold the claim for retry.
- Add a regression where the search endpoint fails while a fixture contributor is already at `CAP`; assert that no `bounty-eligible` label is written and the gate does not close/approve the claim based on a fabricated zero.

---

## Shared root cause

Both findings come from collapsing **transport state** and **business data** into the same sentinel:

```text
GET failed  -> None -> empty collection/object -> normal adjudication
```

For payout logic, absence of evidence must not be treated as evidence of absence. A read required to make a monetary or destructive decision should have three states, not two:

1. successfully read data;
2. authoritative empty/not-found data where that state is meaningful;
3. indeterminate read failure — retry/hold, never approve or reject from it.

## Claim

I am claiming #16471 for this audit and these two concrete defects. No acceptance or payment is asserted until the maintainer verifies them and a payout is independently observed on the RTC wallet.
