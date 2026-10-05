# Cloud staging handoff

Verified 5 October 2026, IST. The next cloud phase starts with private connection setup and read-only account checks. The application still runs locally against SQLite. Prepared analytics scripts do not deploy the website, migrate operational workflows, or enable phone calls.

## Current evidence

| Check | Result |
| --- | --- |
| Snowflake Python connector | Installed: 4.8.0 |
| Named connections | None found; only file paths and TOML section names inspected |
| Selected warehouse | None; no name assumed from the trial account |
| Project configuration | `.local/cloud.toml` created from the example only because absent; connection/warehouse left blank |
| Available Snowflake app tools in this session | None discoverable |
| CoCo executable | Not installed or discoverable |
| Analytics assets | SQL rendered, fictional fixtures exported and validated offline |
| Account metadata / resources / inference | Not contacted, created, or executed |

See [local capability evidence](../output/cloud/capabilities.json), [rendered analytics DDL](../output/cloud/deploy.sql), and [bounded enrichment plan](../output/cloud/enrichment.sql). The exported bundle has 20 fictional customers, 21 loans, 370 payments, and 22 interactions. Its manifest SHA-256 is `22a3f34b4839349e2b065b94e2fba8e4883bd4796265abf9d7c273d14619dd1a`.

## 1. Find your existing account details

Sign in to Snowsight. Open the account selector, choose **View account details**, then use **Connectors/Drivers** or **Config File**. Copy the connector account identifier in `ORG-ACCOUNT` form, without `https://` or `.snowflakecomputing.com`. Use the Snowflake user's login name, which can differ from its display name. In the warehouse list, select an existing warehouse visible to that user/role. Choose `COMPUTE_WH` only if it actually appears. [Official account-identifier instructions](https://docs.snowflake.com/en/user-guide/admin-account-identifier).

The account identifier, login name, and warehouse are configuration metadata. Passwords, MFA codes, private keys, and tokens stay on your machine or in the authentication browser; do not send them through chat.

## 2. Prepare a named connection locally

The configuration helper plans changes by default. Replace the three placeholders below with your existing details. For a native Snowflake password/MFA account:

```powershell
.\.venv\Scripts\python.exe -m scripts.configure_cloud --connection-name samvaad_demo --account "ORG-ACCOUNT" --user "LOGIN" --warehouse "EXISTING_WH" --auth password-mfa
```

Review its plan, then repeat with `--apply` to write local configuration. This operation stores connection metadata without a password; it does not contact Snowflake or create cloud resources. The helper preserves other named connections and refuses conflicting existing values. An existing warehouse name is required; find it in Snowsight before running the helper. Its default target database is `SAMVAAD_STAGING`, with `--database` available for a reviewed alternative. The initial blank template and current rendered example plans use `SAMVAAD_DB`; regenerate those plans after setup to reflect the configured target.

Use `--auth externalbrowser` instead only if your account supports configured browser SSO. Snowflake documents this as an IdP/federated authentication flow; it opens the local browser and can require MFA. It is not a general replacement for a password on every trial account and is unsuitable for unattended server authentication. [Browser SSO prerequisites](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth-use).

The Python connector chooses `~/.snowflake/connections.toml` when that directory exists, with `SNOWFLAKE_HOME` as an override. Otherwise, Windows uses `%USERPROFILE%\AppData\Local\snowflake\connections.toml`. Before setup, neither file nor directory existed here; the installed connector selected the Windows fallback. Project `.local/cloud.toml` contains only the connection reference, target database name, and warehouse. [Named-connection locations](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

Administrator-configured key-pair authentication is another supported option. A production worker can use supported workload identity federation with an appropriately configured cloud identity. Neither is automatically established by the local helper. Keep private keys and tokens outside this repository; follow the account's approved authentication policy. [Connector authentication options](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

## 3. Verify the connection without applying assets

First inspect local configuration, which never connects:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_doctor --config .local/cloud.toml --output output/cloud/capabilities.json
```

For native password/MFA, run the next command yourself in an interactive terminal. Hidden prompts read your password and optional authenticator-app MFA code into memory for this connection and do not persist them. Enter the code locally if your account requires TOTP; otherwise leave that second prompt empty. Trial accounts do not support Duo push, so do not assume a push notification is available. [Connector MFA methods](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect), [trial limitations](https://docs.snowflake.com/en/user-guide/admin-trial-account).

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_doctor --config .local/cloud.toml --connect --prompt-password --output output/cloud/account-metadata.json
```

For an already configured SSO connection, omit `--prompt-password` and complete the browser login/MFA:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_doctor --config .local/cloud.toml --connect --output output/cloud/account-metadata.json
```

The connected doctor reads session account/region/role/version and visible warehouse/model/Search metadata. It does not run AI functions, create schemas, grant roles, or deliberately resume compute. Confirm that authentication succeeds and the selected existing warehouse is visible. A Search metadata error is expected if the target `SAMVAAD_DB` has not been created or is inaccessible; inspect the individual result rather than treating every missing capability as an authentication failure. Metadata visibility alone does not establish trial type, credit balance/expiry, inference privileges, or hosting readiness.

## 4. Review phase-one analytics plans

These commands remain offline unless `--apply` is explicitly added:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_deploy --config .local/cloud.toml
.\.venv\Scripts\python.exe -m scripts.cloud_export --config .local/cloud.toml
.\.venv\Scripts\python.exe -m scripts.cloud_load --config .local/cloud.toml
.\.venv\Scripts\python.exe -m scripts.cloud_enrich --config .local/cloud.toml --limit 5
```

The reviewed default DDL creates `SAMVAAD_DB`, RAW/CORE/AI schemas, fictional-data tables, and Customer 360/evidence views when eventually applied. It contains no account, warehouse, grant, hosted app, Search service, or action-workflow table creation. The importer uses bound values, checksum/count validation, transactional rollback, and one-bootstrap-at-a-time semantics. Enrichment plans up to five interactions, each with intent, sentiment, and entity functions; it remains an analysis job rather than an offer approval mechanism.

After a successful account check, reconcile intended database ownership, existing-warehouse access, credit budget, and regional Cortex permissions before applying. Actual DDL acceptance, fixture reconciliation against Snowflake, and real model outputs are still untested. Optional Search remains separate because indexing and serving can consume credits. See [cloud setup and apply commands](cloud-setup.md).

## 5. Resolve hosting and workflow blockers

| Area | Verified constraint and next work |
| --- | --- |
| Streamlit versions | The local lock pins 1.65.0. Current warehouse-runtime documentation lists versions only through 1.52.2. Container runtime supports later versions with a configured package source; this does not prove our complete dependency set is deployable. |
| Container packages | Pinning 1.65.0 requires an attached artifact repository or configured external package access. Container Python is 3.11; additional operating-system libraries cannot simply be installed. |
| Runtime selection | Explicitly choose warehouse or container when preparing website deployment; do not rely on a default. |
| Operational storage | Trial-compatible production design needs PostgreSQL for atomic approvals, execution claims, offers, consent, and voice/response events, with Snowflake analytics. That adapter is unimplemented. |
| App provider | The shared factory still raises `CLOUD_PENDING` for cloud mode. Cortex jobs are prepared, but no live application Search/Analyst/Agent provider exists. |
| Local voice | Windows SAPI cannot be moved into a Linux Snowflake runtime. Provisioned local Whisper and a guarded demo dialogue do not establish a hosted telephone worker. |
| Identity and public endpoints | Local demo personas/tokens require trusted production identity and customer scoping; public invitations require an HTTPS backend reachable from the chosen frontend. |

The Streamlit version/package findings come from [Snowflake dependency management](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management). A warehouse deployment needs an explicit compatibility port, including current tab-event behavior, before it can be claimed supported. Both Snowflake runtimes use Linux, so the Windows speech implementation needs replacement or a separate voice worker. [Runtime comparison](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments). The existing `app/environment.yml` is a scaffold, not an accepted deployment specification.

When the 2026_06 behavior bundle is enabled, newly created Streamlit apps default to `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`. A container app requires a usable existing compute pool or account default, appropriate `USAGE`, and auto-resume; the default changed from warehouse runtime. We have not inspected those account settings or provisioned a pool. [Current runtime-default change](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2342).

Hybrid tables are unavailable in trial accounts and Google Cloud. Therefore standard-trial credits cannot supply the hybrid-table workflow design; the PostgreSQL-plus-analytics proposal is an architectural recommendation until implemented and tested. [Hybrid availability](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations). Standard Snowflake PRIMARY KEY/UNIQUE/FOREIGN KEY declarations do not enforce the required operational guarantees. [Constraint behavior](https://docs.snowflake.com/en/sql-reference/constraints-overview).

## 6. Verify CoCo eligibility independently

CoCo is currently missing. Snowflake documents a paid account or dedicated CoCo CLI trial; a standard Snowflake trial is unsupported. Confirm which account you have before relying on trial credits for the hackathon automation. [Official CoCo account/setup requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

After installing and configuring an eligible account, `python -m scripts.cloud_coco_check` checks actual version/help without a model request. Its optional `--run-smoke` makes a bounded real model request and requires an exact marker. That proves model authentication only; actual project skill discovery and hook invocation require a separate recorded runtime demonstration.

The immediate handoff is ready: supply the existing account metadata privately through the local helper, then perform the read-only doctor check. No website deployment, workflow migration, live call, or production-readiness claim is made by this preparation.

## Trial budget and AI availability

The owner reports a dashboard balance of $400 remaining and six days until trial expiry. This is user-reported, not a connector billing check. Snowflake suspends a trial when its duration ends or its balance is exhausted; unused trial balance expires if the account is not upgraded. Self-service trial AI features are disabled by default until a credit card is added. Adding a card and upgrading are separate actions; neither has been performed by this project. Account billing changes must be made by the owner through Snowflake. Inspect analytics/storage first, then verify actual Cortex enablement before running enrichment. [Official trial conditions](https://docs.snowflake.com/en/user-guide/admin-trial-account).

The current trial also excludes external network access. This constrains frontend access to an external operational backend and PyPI-only package retrieval. A container/runtime port and usable account features must be validated before choosing app hosting. Do not treat a visible Apps/Postgres menu as proof that an instance, compute pool, external integration, or service is enabled.

If the connection-settings menu is difficult to find, use **Projects → Workspaces → + Add New → SQL File**, then run the following statements separately. They reveal metadata, without creating a warehouse or application:

```sql
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT_IDENTIFIER,
       CURRENT_USER() AS LOGIN_NAME,
       CURRENT_ROLE() AS ROLE_NAME,
       CURRENT_WAREHOUSE() AS WAREHOUSE_NAME;
SHOW WAREHOUSES;
```

A NULL current warehouse means none is selected in that editor session; use an actual visible name from SHOW WAREHOUSES. [Current Workspaces navigation](https://docs.snowflake.com/en/user-guide/ui-snowsight/workspaces-working), [connection metadata queries](https://docs.snowflake.com/en/user-guide/gen-conn-config).
