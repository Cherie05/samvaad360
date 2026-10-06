# Security and deployment scope

Samvaad 360 is a synthetic lending prototype. It is **not approved for real customer data or production financial execution**. See [the current release gates](docs/production-readiness.md).

The public website uses a restricted Snowflake reader and fixed fictional tables. Visitor reviews, onboarding and conversations stay within a visit. Its shared snapshot, admission controls and statement reservations reduce application query activity; they are not a distributed edge defense or an account-wide credit cap.

The private local API enforces operator scopes, approval roles, consent, idempotency, bounded requests and expiring customer capabilities. Local operator personas are demonstration identities. Production needs enterprise identity, strong borrower authentication, durable operational storage and verified lender/carrier connections.

Real calling, SMS and financial changes are disabled on the public demonstration. The carrier adapter is a separate controlled-pilot integration; transport tests do not prove an actual delivered call.

Keep secrets in private deployment settings. `.local/`, databases, invitation logs, keys, credentials and recordings of login screens must stay out of publication. A source-pattern scan is one check, not proof that every possible secret or vulnerability is absent.

For a suspected vulnerability, use the repository's **Security → Report a vulnerability** option when available. Do not disclose credentials, real personal data or active invitation capabilities in a public issue.
