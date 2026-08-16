# Contributing to Louis OS

## Payment / bounty policy

Repository issues are **not paid bounties by default**. A payment obligation exists only when the repository owner explicitly labels an issue as a paid bounty and the issue itself states all of the following:

1. reward amount and currency;
2. acceptance criteria;
3. payment method or escrow path;
4. eligibility rules;
5. an explicit statement that external contributors may claim the bounty.

Internal issues may contain words such as `bounty`, `reward`, `cash`, `USDC` or `paid` because Louis OS researches external work. Those words do not offer a reward for modifying Louis OS itself.

Unsolicited pull requests that claim an internal issue as a bounty may be closed without payment.

## Pull requests

- Keep changes narrowly scoped and explain the root cause.
- Add or update deterministic tests for behavior changes.
- Do not include secrets, private keys, access tokens, private user data or copied third-party credentials.
- Do not weaken `config/production_policy.json`, the kill switch, economic truth accounting or external-action gates without explicit owner authorization.
- Do not add autonomous payment, purchase, contract-signature, KYC/CAPTCHA bypass, gambling or unauthorized-security behavior.
- External marketplace adapters must report unknown metrics as unknown rather than fabricating confidence/competition/effort values.

## Production-impacting changes

Changes affecting workflows, credentials, wallets, VM execution or outbound external actions must pass ATLAS CI and should be reviewed against the production policy before merge.
