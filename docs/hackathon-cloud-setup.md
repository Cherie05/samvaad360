# Samvaad 360: new hackathon account to hosted demo

Updated 5 October 2026, IST, for account `ZYLTUKM-HU63768`, login `ARUNVPP24`. The owner confirms using the organizer activation link. A bounded `llama3.3-70b` request succeeded; current credits/expiry and actual CoCo eligibility still require account-side checks.

**Current execution:** resources exist in AWS_AP_SOUTHEAST_7, the synthetic import reconciled, and the private `SAMVAAD360` app works. [The latest GitHub release](https://github.com/Cherie05/samvaad360/actions/runs/37338447835) passed **218 tests**, authenticated with OIDC, uploaded the app and verified 20 customers and live-file recovery. The owner confirms all four main tabs and the saved reviewer note. `output/cloud/trial/result.json` records current evidence alongside the historical initial release. Setup is completed; use **Step 4** for additional rehearsal and [GitHub deployment](github-deployment.md) for code updates.

**Hosted startup repair:** explicit Python 3.11.15, Streamlit 1.52.2 and Snowpark 1.55.0 pins resolved the original launcher failure for this app. See [the repair history](cloud-startup-repair.md). GitHub diagnosis uses the configured OIDC identity; another personal password prompt is not needed for that workflow.

## What will be hosted

| Component | Hackathon cloud implementation |
| --- | --- |
| Website | Private Streamlit in Snowflake app `SAMVAAD_STAGING.APP.SAMVAAD360`, warehouse runtime, Python 3.11.15, Streamlit 1.52.2 and Snowpark 1.55.0 |
| Backend | Python/Snowpark in the same Snowflake-hosted app; bound queries reuse the tested lending rules |
| Customer database | Snowflake RAW tables and CORE Customer 360/evidence views: 20 customers, 21 loans, 370 payments, 22 interactions, all fictional |
| Review state | Persistent `APP.DEMO_REVIEWS` with current-consent/proposal rechecks; a single-operator synthetic demonstration |
| AI | Optional customer-scoped, bounded Cortex AI_COMPLETE requests; separate bounded intent/sentiment/entity enrichment |
| Automation | CoCo CLI installed locally; live account/model, project skill and hook demonstrations remain required |
| Audio and phone calls | Existing Windows speech/Whisper lab remains local. Cloud app displays transcripts and handoff scripts; carrier/media worker and production voice integration remain pending |

The cloud demo has no browser persona selector. It reads the real Snowsight viewer from `st.user.user_name`, fails closed without that identity, and initially permits only `ARUNVPP24`. `CURRENT_USER()` is not a viewer identity in an owner's-rights app. [Official identity behavior](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/personalization).

The older supported warehouse Streamlit version has two upstream advisories. One is Windows-specific; the other involves caching APIs the shipped app does not use. This restricted Linux/synthetic demonstration retains those findings and is not a clean production dependency gate. Do not start a Windows server with the isolated compatibility version. See the [runtime advisory review](cloud-runtime-advisories.md) before expanding the demo.

This is a new hosted hackathon demonstration, not a production migration of every local workflow. Existing local financial approvals, invitation endpoints, voice sessions and protected execution service are not copied into the cloud review ledger. Demo reviews cannot send messages, approve real loans, change rates/premiums or make calls. Independent production approvers, transactional operational storage and deployed public/API/voice services remain separate work. Standard Snowflake tables do not enforce the operational uniqueness/foreign-key guarantees needed for financial execution.

## Step 1: confirm the participant account and deadline

In the dashboard's account selector, confirm the account is `ZYLTUKM-HU63768`. Open its trial/credits panel and confirm the organizer credits and expiry there. No payment method, paid upgrade, account-wide AI allowlist or cross-region setting is changed by our setup.

The public event page lists prototype submission **13 September–4 October 2026**, evaluation **5–22 October**, and demo days **27–30 October**. As of 5 October, check the authenticated participant portal for an extension or permission to update an existing submission. The app matches the event's Customer 360 / Next Best Action track; actual CoCo evidence is still required before claiming that integration. [Event track and timeline](https://hack2skill.com/event/cococlihack-gccedition/).

The organizer activation link is the intended route. Snowflake distinguishes a dedicated CoCo trial from a standard Snowflake trial; standard trials do not support CoCo. If the organizer account reports that AI/CoCo is disabled, ask the organizer to verify activation for this account. Do not create a second unrelated account or upgrade merely to conceal that error. [CoCo account requirements](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

## Step 2: run the prepared private setup command

The package and plan are already generated under `output/cloud/trial`. Review `01-bootstrap.sql`, `02-schema.sql`, `03-publish.sql`, `plan.json`, and the six-file app bundle. They contain configuration metadata and fictional data, without passwords, keys, local database files or voice-model weights.

Open PowerShell in this workspace and run:

```powershell
Set-Location -LiteralPath 'C:\Users\arunv\Documents\coco-snowflake'
.\.venv\Scripts\python.exe -m scripts.trial_cloud_setup --account 'ZYLTUKM-HU63768' --user 'ARUNVPP24' --apply
```

The convenience entry point performs the same operation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\enter_cloud.ps1
```

Enter the native Snowflake password and optional authenticator-app MFA code in the hidden terminal prompts. Keep them out of chat, command arguments and screenshots. No password is written to a connection file. Leaving the password blank cancels before authentication. If this is an SSO-only account, use its approved browser connection method and the manual dashboard path below; do not paste secrets or assume `externalbrowser` is supported for every native trial login.

Omitting `--apply` only regenerates a local offline plan; it never connects or creates resources. Defaults are:

| Setting | Value |
| --- | --- |
| Dedicated app/setup role | `SAMVAAD_HACKATHON`, granted to the named user and SYSADMIN |
| Warehouse | `SAMVAAD_XS`, X-Small, standard, initially suspended, auto-resume, auto-suspend after 60 seconds |
| Warehouse query timeouts | 60 seconds execution / 30 seconds queued |
| Resource monitor | `SAMVAAD_DAILY_LIMIT`, five warehouse credits daily, notifications at 80%, graceful suspension at 90%, immediate suspension at 100% |
| Database | `SAMVAAD_STAGING` |
| Named local connection | `samvaad_hackathon`, credential-free metadata |

The sequence verifies account/user before provisioning; checks for conflicting existing warehouse/monitor settings; creates resources; switches off secondary roles and uses the dedicated role; creates analytical tables, views and demo ledger; imports/reconciles the synthetic bundle; verifies and uploads only the six manifest files; explicitly creates a warehouse-runtime Streamlit app; publishes its live version; reconciles Customer 360 count; saves local connection metadata.

No privilege is granted to PUBLIC, no unrelated warehouse is resumed, and no Search index, background task, compute pool, telephone trunk or AI request is created automatically. The app role receives database USAGE/CREATE SCHEMA and usage/operate on its warehouse, rather than account-wide CREATE DATABASE.

DDL stages commit independently. On a failure, completed steps remain in `output/cloud/trial/result.json`; partial resources are not silently dropped. Repeated fixture imports with the identical manifest return an already-loaded result. Existing `SAMVAAD360` apps are preserved and produce `APP_ALREADY_EXISTS`: open/review the existing app instead of silently replacing it. Never clear a shared or real database to retry this demo.

## Step 3: dashboard-only bootstrap alternative

In Snowsight, choose **Projects > Workspaces > + Add New > SQL File**. Select `ACCOUNTADMIN` in the role picker and paste/run `output/cloud/trial/01-bootstrap.sql`. These statements create the warehouse, monitor, database, role and stage. [Workspaces navigation](https://docs.snowflake.com/en/user-guide/ui-snowsight/workspaces-working).

If ACCOUNTADMIN is unavailable, an account owner/admin must run this reviewed file or provide equivalent scoped grants; the helper does not invent privileges. Once bootstrap succeeds, use the previous command with `--skip-bootstrap` to authenticate directly as `SAMVAAD_HACKATHON` and continue schema/import/app deployment. For an already approved SSO-only account, configure an `externalbrowser` named connection using `scripts.configure_cloud`, apply `02-schema.sql` in Snowsight, load the fixture with `scripts.cloud_load --fixture output/cloud/trial/fixtures.json --apply`, then upload the six `output/cloud/trial/app` files to the release stage/path from `plan.json` and execute `03-publish.sql`. Use the same database and `SAMVAAD_XS`; inspect the configured target before running any command. [Named connections and authentication](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect).

Do not paste `03-publish.sql` until the app files have actually been uploaded to its exact stage path. Source files are copied once when the app is created. The setup explicitly sets `RUNTIME_NAME='SYSTEM$WAREHOUSE_RUNTIME'`, avoiding a container default/compute-pool requirement. [CREATE STREAMLIT](https://docs.snowflake.com/en/sql-reference/sql/create-streamlit), [supported Streamlit versions](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management).

## Step 4: open and verify the cloud website

In Snowsight, choose role `SAMVAAD_HACKATHON`, then **Projects > Streamlit > SAMVAAD360**. It is a signed-in Snowflake website, not an anonymous public borrower portal. Keep the allowlist and app grants private while using synthetic data.

Check these journeys:

1. C0001: repayment hardship -> supportive callback recommendation, with the supporting conversation excerpt.
2. C0002: competitor/foreclosure intent -> capped retention proposal, requiring a review.
3. C0003: top-up intent -> conditional invitation proposal; request a demo review and save a demo decision. Refresh the app and confirm it persists in Snowflake.
4. C0004: DND/consent restriction -> no request button allowed.
5. Ask with evidence initially uses an explicit deterministic summary. Confirm the selected customer's sources appear and an explicit request about another customer is rejected.
6. Attempt “approve and send this offer”: the question cannot perform the action.

The published DDL and reconciled rows do not by themselves prove hosted browser behavior. Record these results separately; screenshots/video for the judges should show the actual hosted app. If the editor asks to acknowledge Anaconda package terms, review/accept them in your Snowflake account as the account owner; setup does not silently accept a legal agreement.

## Step 5: enable and verify bounded Cortex usage

[The account capability check](https://github.com/Cherie05/samvaad360/actions/runs/37338451069) returned `OK` from the default model using a fixed synthetic prompt and 16-token output cap. It proves model access. The customer-scoped answer and batch enrichment below still need live quality checks.

For an actual AI-backed answer, open **Ask with evidence**, check **Use Cortex AI for this answer**, and submit one customer question. The default model is `llama3.3-70b`; output is limited to 512 tokens, context is scoped/bounded, and the generated response is marked for review against its source excerpts. Only the submit event calls the model. It cannot alter approvals. The account must permit that model in its region or through already approved account settings. Do not enable cross-region processing merely to bypass a model error.

For batch transcript intent/sentiment/entity extraction, start with five interactions:

```powershell
.\.venv\Scripts\python.exe -m scripts.cloud_enrich --config .local/cloud.toml --limit 5
.\.venv\Scripts\python.exe -m scripts.cloud_enrich --config .local/cloud.toml --limit 5 --apply --prompt-password
```

The first command only renders the plan. The second consumes credits and stores reviewable AI results. Inspect `error_rows` and the app's **Cloud AI enrichment for human review** section. AI outputs do not override the deterministic contact/affordability/consent policy. [AI_COMPLETE parameters](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string).

## Step 6: CoCo and hackathon evidence

CoCo 1.1.87 is installed at the native path recorded in `output/cloud/coco-install.json`; official archive SHA-256 was checked. Existing versions/user PATH were preserved. The project discovery helper now recognizes version directories. Version/help checks do not establish account/model access.

Activate the project virtual environment, then launch the native executable shown in that report. Use its interactive account wizard or select the configured connection if its authentication method is supported. Complete authentication privately in that terminal/browser. Verify the account is `ZYLTUKM-HU63768` and use the dedicated app role for app data operations. Do not store a password just to make a noninteractive smoke command succeed.

```powershell
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m scripts.cloud_coco_check --output output/cloud/coco-capabilities.json
# After private CoCo authentication/compatible connection configuration:
.\.venv\Scripts\python.exe -m scripts.cloud_coco_check --run-smoke --output output/cloud/coco-model-check.json
```

In the actual CoCo session, use `/skill list` and verify the Samvaad project skills are discovered. Demonstrate a safe customer/evidence query or help reviewing the prepared SQL. The existing generate/approved-runner/reset skills target the **local** operational backend; their execution is not a cloud financial workflow. Their advisory hooks and the local service enforce the local simulation policy. A hosted cloud review record is not executable by those skills. Record actual project hook invocation separately rather than equating a model smoke response with hook integration.

For submission, retain hosted Customer 360 screenshots/video, one actual Cortex answer with evidence, the capped batch extraction check, actual CoCo skill/hook usage, repeatable setup files, fixture manifest and test report. Use a consent/DND or hardship scenario as the guardrail demonstration.

## Step 7: control usage and keep a handoff

Five credits is a warehouse quota, not five dollars and not a whole-account budget. Resource monitors do not cap serverless AI, CoCo, storage or other services. Keep initial AI requests bounded, avoid provisioning Search until necessary, close the app/editor tabs after rehearsal, and inspect **Admin > Cost management** and the trial panel daily. Do not assume that closing the tab immediately stops a running query; auto-suspend/monitor protection is separate. [Warehouse monitors](https://docs.snowflake.com/en/user-guide/resource-monitors), [trial credits and expiry](https://docs.snowflake.com/en/user-guide/admin-trial-account).

When no workload is running, an owner may suspend this dedicated warehouse explicitly:

```sql
USE ROLE SAMVAAD_HACKATHON;
ALTER WAREHOUSE SAMVAAD_XS SUSPEND;
```

Auto-resume lets the next app query start it again, so this is not a permanent spending lock. Keep exports, source and recorded demo outside the trial account before expiry. A trial may suspend even with an unused balance. Organizer-specific credit validity remains to be checked in the account/participant portal.

## Checks and leftovers

Offline preflight covers source/SQL packaging, credential boundaries, wrong-account refusal, existing-resource conflict refusal, viewer/customer scope, contact-policy rechecks, synthetic review persistence and app rendering. The warehouse-compatible app was exercised on **Streamlit 1.52.2** with a recording Snowpark test session. This does not test Snowflake SQL acceptance, hosted package resolution, hosted identity delivery or live AI output.

Provisioning/import, GitHub deployment and main-app startup are complete. The owner reports four tabs and a saved reviewer note; one fixed-prompt Cortex connection request returned `OK`. Pending: exact approved-review status after a manual refresh, grounded Cortex answer/enrichment quality, CoCo account authentication/skills/hooks, balance/expiry verification and participant-portal acceptance. Production remains blocked on independent approvers, customer/tenant permissions, transactional operational storage, public HTTPS/API workflows, durable execution/recovery, observability/backups, real policy/model validation and licensed production voice/media/carrier. See [production readiness](production-readiness.md) and [telecalling plan](telecalling-plan.md).

