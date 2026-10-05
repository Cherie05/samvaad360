# Executable Snowflake and CoCo preparation

The local product remains on the tested SQLite service. The new `cloud/` package prepares a real analytical data layer and bounded Cortex jobs, but does not implement `SnowflakeService`, production identity, cloud action execution, or website deployment. No Snowflake account was contacted while preparing these assets. Offline tests verify configuration rejection, parameter binding, fixture integrity, bootstrap rollback, and CLI behavior; they do not prove that Snowflake accepted the SQL.

## Prepared assets

| Asset | Behavior |
| --- | --- |
| `cloud/config.py` | Named connection reference, conservative SQL identifiers, credentials excluded from project config |
| `cloud/sql/001_schema.sql` | RAW tables for fictional customers, loans, payments, and interactions; AI result table |
| `cloud/sql/002_views.sql` | Customer 360 financial aggregates and cited interaction evidence; closed loans excluded from active obligations |
| `cloud/sql/003_search.sql` | Optional Cortex Search service, filtered by customer/interaction/channel attributes, scheduled initialization |
| `cloud/sql/004_enrichment.sql` | Bounded intent, sentiment, and entity extraction, preserving raw model outputs for review |
| `cloud/fixtures.py` | Reproducible synthetic fixture bundle with manifest checksum; bound-value import into empty analytics tables |
| `cloud/capabilities.py` | Local prerequisite report, optional metadata-only account discovery, actual CoCo version/help/model verifier |

No script creates an account, warehouse, privileged role, grant, or cloud action table. Commands plan or validate by default. `--apply` uses an already selected warehouse and can resume it according to the warehouse's own settings. Warehouse queries, Cortex functions, and Search indexing/serving consume credits when explicitly run.

## Connection setup

Install optional cloud dependencies in the existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cloud.txt
Copy-Item -LiteralPath cloud\config.example.toml -Destination .local\cloud.toml
```

Edit `.local/cloud.toml` with a configured connection name, a new demo database name, and an existing warehouse. Store authentication privately in Snowflake's `connections.toml`, using your organization's approved authentication. Neither project config nor command arguments accept a password, token, or private key. Snowflake's connector supports named connections and documents the Windows config locations. [Connector connection setup](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

```toml
[snowflake]
connection_name = "samvaad_demo"
database = "SAMVAAD_DB"
warehouse = "YOUR_EXISTING_WAREHOUSE"
```

Run local checks first, then optionally read account metadata:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_doctor --output output/cloud/capabilities.json
.\.venv\Scripts\python.exe -m scripts.cloud_doctor --connect
```

The second command only queries session metadata, visible warehouses/models, and existing Search services. It does not call AI functions, create resources, or resume a warehouse deliberately. Metadata visibility alone does not prove Cortex function access, account type, application identity, or hybrid-table support.

## Review and apply analytical data assets

These commands work without an account and produce concrete reviewable files:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_deploy
.\.venv\Scripts\python.exe -m scripts.cloud_export
.\.venv\Scripts\python.exe -m scripts.cloud_load
.\.venv\Scripts\python.exe -m scripts.cloud_enrich --limit 5
```

Outputs are `output/cloud/deploy.sql`, `fixtures.json`, and `enrichment.sql`. The default fixture reference is explicitly fixed at 5 October 2026 UTC for reproducibility. Pass a timezone-aware `--reference` to create another dated demo. The standard bundle contains 20 customers, 21 loans, 370 payments, and 22 interactions; contacts remain masked/reserved fictional values.

After configuring the account and reviewing the SQL, these commands perform real work:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_deploy --apply
.\.venv\Scripts\python.exe -m scripts.cloud_load --apply
.\.venv\Scripts\python.exe -m scripts.cloud_enrich --limit 5 --apply
```

The loader refuses populated tables containing another or incomplete dataset. It validates manifest checksums and unique fixture IDs, stages values with connector bind parameters, and rolls back if the loaded counts/checksums differ. An identical completed import is a no-op. Run one loader at a time: standard-table constraints do not provide a concurrent import uniqueness guarantee. This is an analytics bootstrap, not a cloud workflow migration.

Cortex jobs analyze borrower evidence rather than agent speech. Results retain the source hash and provider label. Intent/sentiment functions preserve error information; extraction retains the raw response. Unknown, negated, or inconsistent financial facts require review. This job does not map categorical sentiment to the local numeric score or use model text to approve offers. Live inference requires suitable role access and regional/model availability. [AI_CLASSIFY](https://docs.snowflake.com/en/sql-reference/functions/ai_classify), [AI_SENTIMENT](https://docs.snowflake.com/en/sql-reference/functions/ai_sentiment), [AI_EXTRACT](https://docs.snowflake.com/en/sql-reference/functions/ai_extract).

To prepare/apply optional Search, use `cloud_deploy --include-search` and then `--apply`. Initialization is scheduled one hour later. Serving auto-suspend is 1800 seconds, the documented minimum; this does not suspend indexing. When finished, an authorized operator can suspend both layers in Snowsight:

```sql
ALTER CORTEX SEARCH SERVICE IF EXISTS SAMVAAD_DB.AI.INTERACTION_SEARCH SUSPEND;
```

Adjust the database name to your configuration. [Create Search](https://docs.snowflake.com/en/sql-reference/sql/create-cortex-search), [Search suspend and cost controls](https://docs.snowflake.com/en/sql-reference/sql/alter-cortex-search).

Search operates with the service owner's rights. Backend authorization must establish which customer an operator may access, then enforce that customer filter on every query. A caller-selected filter is insufficient. No broad user grants or direct browser Search calls are created here. [Search access model](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/query-cortex-search-service).

## Trial-account operational state

Snowflake standard-table PRIMARY KEY, UNIQUE, and FOREIGN KEY declarations do not supply the same enforced guarantees as the local SQLite action/response transactions. Approvals, execution claims, event IDs, offers, consent changes, and outbox deliveries need atomic operational storage. [Snowflake constraint overview](https://docs.snowflake.com/en/sql-reference/constraints-overview).

Hybrid tables provide enforced constraints, but current documentation excludes trial accounts and Google Cloud. Therefore the trial-compatible deployment should use PostgreSQL for operational workflows and Snowflake for Customer 360/Cortex analytical data, or evaluate hybrid tables after moving to an eligible paid account. This is an architecture decision; a PostgreSQL or hybrid implementation has not been fabricated here. Port the service guards and concurrent execution/response tests before enabling cloud writes. [Hybrid-table constraints and limitations](https://docs.snowflake.com/en/user-guide/tables-hybrid-limitations).

## Actual CoCo verification

Snowflake currently requires a paid account or a dedicated CoCo trial; standard Snowflake trial credits do not establish CoCo eligibility. Install/configure CoCo using its official instructions, then run:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_coco_check --output output/cloud/coco-capabilities.json
.\.venv\Scripts\python.exe -m scripts.cloud_coco_check --run-smoke
```

The verifier really checks the discovered executable's version/help. The optional smoke sends one bounded private request and only passes if CoCo exits successfully and returns the exact random marker. It prints no provider output or credentials. This establishes model authentication only. Code mode disables skills, so the report deliberately leaves project skills and runtime hooks unverified. [CoCo account/setup requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli), [Verified CLI flags](https://docs.snowflake.com/en/user-guide/cortex-code/cli-reference).

After model smoke succeeds, use an interactive CoCo session from this repository, inspect `/skill list`, invoke `samvaad-generate` on a synthetic customer, and run the approved runner only after a separate demo operator approves. Record the real session outcome and exercise a blocked execution to prove the hook is invoked. Existing Python hook tests prove its code contract; they do not substitute for that runtime check.

## Remaining account-dependent checks

The current machine has no named Snowflake connection or selected warehouse and no discoverable CoCo executable. Its capability reports preserve that evidence. Required external inputs are an enabled account/connection, approved authentication, existing warehouse and privileges, and CoCo model availability. Website hosting, trusted operator identity, a transactional cloud workflow adapter, Cortex evaluation, and live delivery checks follow those prerequisites. The local backend intentionally raises `CLOUD_PENDING` if asked to switch to Snowflake now.
