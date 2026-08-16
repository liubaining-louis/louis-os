# Security Policy

Louis OS can interact with external marketplaces, cloud infrastructure and wallets. Security reports should therefore avoid public disclosure of exploitable secrets or active credentials.

## Supported security expectations

- Never commit API keys, private keys, seed phrases, session cookies or access tokens.
- Production workers must run with least privilege and only the secret files they require.
- External economic actions must pass `config/production_policy.json` and the shared policy gate.
- The global kill switch must fail closed.
- Payments, purchases, contract signatures, credential changes, KYC/CAPTCHA bypass, mandatory staking, gambling/speculation, deceptive engagement and unauthorized security testing are not autonomous actions.
- Revenue must not be booked without independently verifiable evidence.

## Reporting a vulnerability

Do not open a public issue containing a live secret, private key or immediately exploitable credential. Contact the repository owner privately through the account's established private contact channel and include a minimal reproduction, affected component and remediation suggestion.

If a public issue is safe, redact sensitive values and provide only the minimum details needed to reproduce the defect.

## Emergency response

The owner can set `kill_switch` to `true` in `config/production_policy.json` to stop maintained outbound economic paths. Any workflow that bypasses the shared production policy is a security defect and should be treated as high priority.
