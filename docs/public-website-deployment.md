# Public website with a Snowflake backend

The public lender prototype uses Streamlit Community Cloud for its browser UI and Python backend, and this hackathon account for live analytical reads. Community Cloud hosting is free; Snowflake warehouse queries consume account credits. The existing private Snowsight app remains the operator demonstration.

**Verified public website:** [samvaad360.streamlit.app](https://samvaad360.streamlit.app/). **Public source:** [Cherie05/samvaad360](https://github.com/Cherie05/samvaad360). The hosted public browser passed **20 checks** at **2026-10-06T15:00:27.839489Z**, and the local public browser passed **20** at **2026-10-06T14:59:04.862553Z**. Both observed a genuine Snowflake snapshot of 20 fictional customers and six public workspaces, including Customer hub. The private local relationship browser passed **six end-to-end checks** at **2026-10-06T14:51:38.877300Z**. [GitHub run 37483107870](https://github.com/Cherie05/samvaad360/actions/runs/37483107870) passed **557 tests in 81.51 seconds** for source `7a619e718508777ee491bcf78309b0b2a8f0d7c3`. Deployment job `112337447935` succeeded, confirming 20 customers and `LIVE_VERSION_READY`. Community Cloud does not directly report its commit. The deployment steps below also serve as recovery instructions.

| Component | Public deployment |
| --- | --- |
| Frontend and Python backend | `public_app/streamlit_app.py` on Streamlit Community Cloud, Python 3.11 |
| Database | `SAMVAAD_STAGING.PUBLIC_DEMO` in account `ZYLTUKM-HU63768` |
| Server identity | `SAMVAAD_PUBLIC_SERVICE`, authenticated with an encrypted RSA key stored only in hosting Secrets |
| Permissions | `SAMVAAD_PUBLIC_READONLY`: database/schema/warehouse usage and SELECT on four approved fictional snapshots |
| Customer journeys | 20 fictional customers; hardship, retention, top-up and DND examples |
| Customer hub | Sixth workspace; visit-only fictional onboarding, source links/imports and requests/withdrawals; no shared CRM or customer contacts |
| Public review workflow | Per-visit simulation, without database writes or staff identity |
| Decision workbench | Portfolio priorities, readable policy checks, omnichannel evidence and what-if changes using the actual lending rules |
| Call studio | Review-gated browser conversation, click-to-play voice controls, typed replies, evidence-driven policy changes and downloadable transcript; no carrier dialing |
| Telephone controls | Separate staff-authenticated Twilio API bridge; disabled until provider, HTTPS API and authorised destinations are configured; public reviews cannot authorise calls |
| Visualisations | Overdue exposure, intervention mix, repayment/conversation timeline, explicit rule contributions and observed signal coverage |
| Visitor spend protection | Shared hourly snapshots and host-local reservations; 8 application statements/hour and 64/day; no public refresh or arbitrary SQL; host replacement can reset storage |
| Evidence answers | Deterministic summaries with transcript citations; no public Cortex calls |
| Backup when the trial is unavailable | Checked fictional JSON bundle, prominently labelled offline; never described as a live Snowflake response |

The raw public adapter admits seven fixed, bounded read queries. The hosted `GuardedSnapshotReader` reserves five application statements before an hourly refresh: one identity check and four portfolio reads. It closes the connection and serves all customer/evidence/review workflows from independent memory copies. The host budget permits at most 12 full refresh attempts per UTC day; failed attempts remain charged. Stale Snowflake snapshots are dated and a bundled fallback is clearly labelled. The counter does not measure connector-internal traffic or billed credits, and host replacement can reset its storage. The existing X-Small warehouse auto-suspends after 60 seconds and has a separate five-credit daily warehouse monitor. That monitor is not an account-wide spending guarantee. See [protection and managed-IP setup](enterprise-release-plan.md).

The seeded Snowflake snapshot remains unchanged by Customer hub. Its new records and preferences are visit-only; the actual private staff/API relationship flow is local and durable in SQLite. The private relationship writer/schema have not been configured/applied, and no automatic lender CRM connection exists. See [relationship setup and boundaries](customer-relationship-plan.md).

Admission on this free host uses shared anonymous limits. Reported Streamlit IPs and arbitrary forwarded headers are not trusted security identities. The prepared managed NGINX peer-IP limits and future signed-edge identity support are not deployed on Community Cloud.

## Deploy from the signed-in Create app screen

1. Choose **Create app > Yup, I have an app**.
2. Enter these fields:

   | Field | Value |
   | --- | --- |
   | Repository | `Cherie05/samvaad360` |
   | Branch | `main` |
   | Main file path | `public_app/streamlit_app.py` |
   | Optional subdomain | `samvaad360-demo` if available; otherwise leave blank |

3. Open **Advanced settings** and select **Python 3.11**.
4. On the owner computer, run the following helper. It copies the service settings directly to the clipboard without displaying them:

   ```powershell
   .\scripts\copy_public_secrets.ps1
   ```

5. Paste with **Ctrl+V only into the Secrets box**, click **Save**, then **Deploy**. Keep this credential out of chat, source control, screenshots and submission artifacts. It is a dedicated reader key; the website does not need the owner's password or MFA code.
6. For a private source repository, open the app's **Settings > Sharing > Who can view this app** and choose **This app is public and searchable**. Website visibility and repository visibility are separate settings.
7. Copy the actual assigned `https://...streamlit.app` URL. An optional subdomain is a suggestion until deployment confirms it. Open the link in an incognito window and confirm the sidebar says **Data source: Snowflake** and six workspaces appear: Command center, Customer 360, Evidence desk, Review queue, Call studio and Customer hub.

If the sidebar says **offline synthetic snapshot**, the website is functioning in backup mode; live Snowflake connectivity has not passed for that hosting instance. Check its private logs/settings rather than presenting the fallback as a cloud database result.

During fresh anonymous verification, Community Cloud displayed **“This app has gone to sleep due to inactivity”** before startup. Click **“Yes, get this app back up!”**, wait for the app to load, then check its data-source label and rerun verification. That historical wake was followed by a successful 15-check run; the current relationship release passes 20 checks. Free-host sleep and cold starts mean this prototype does not provide a production availability guarantee; no fixed wake duration was measured.

## Verification and ongoing updates

[GitHub run 37483107870](https://github.com/Cherie05/samvaad360/actions/runs/37483107870) passed **557 tests in 81.51 seconds** for source `7a619e718508777ee491bcf78309b0b2a8f0d7c3`. Deployment job `112337447935` succeeded, confirming 20 customers and `LIVE_VERSION_READY`. Local validation passed **555 tests in 78.18 seconds** in the full suite, followed by a **14-test targeted pass** including two additional engine fact cases. CI covers the complete 557-test suite. The hosted public browser passed **20 checks** at **2026-10-06T15:00:27.839489Z**, and the local public browser passed **20** at **2026-10-06T14:59:04.862553Z**. Both observed a genuine Snowflake snapshot of 20 fictional customers and six public workspaces, including Customer hub. The private local relationship browser passed **six end-to-end checks** at **2026-10-06T14:51:38.877300Z**. Public checks add applicant/review/import/request/opt-out and mobile hub/isolation to earlier charts, evidence and governed conversations. Browser audio audibility and actual telephone delivery remain unverified. The local dependency audit retains zero known advisories across 103 distributions; private runtime advisories are tracked separately.

For a distinctive demo, choose Imran, request and approve a simulation review, then start Call studio. Complete permission and fictional identity checks before submitting `I lost my job`. His conditional top-up stops, the actual quote appears as new evidence, and the conversation ends with human handoff. Separately, Kabir's job-loss what-if changes his reminder to hardship support. Neither demonstration changes saved financial data or claims a validated churn prediction.

After deployment, run this independent check with the actual URL:

```powershell
.\.venv\Scripts\python.exe -m scripts.public_browser_check --url 'https://samvaad360.streamlit.app/'
```

The browser uses fresh contexts without owner cookies or hosting credentials. It checks the application iframe inside the Community Cloud wrapper, expects a live Snowflake source, tests the workflow, and records success only after all checks pass. Hosted reports/screenshots are ignored under `output/cloud/public-browser/hosted/`; local evidence remains in the parent folder. The explicit `--allow-snapshot` option can check backup-mode UI; its report still records the actual source and cannot mark that backend as live.

Community Cloud redeploys source changes from GitHub. Dependencies are pinned in `public_app/requirements.txt`; root `.streamlit/config.toml` provides the theme. The existing GitHub Actions workflow also tests the full application and releases the private Snowflake operator app with OIDC. It never uploads the public reader's private key.

## Submission and production limits

The participant portal supplied by the owner lists **6 October 2026, 11:59 PM IST** as the submission deadline. It requires a public source repository, deployed URL, brief, CoCo CLI video and organizer-template PDF deck. Publishing the website does not automatically make the source public or supply the CoCo/video/deck evidence.

This is a synthetic hackathon prototype. Browser speech uses the visitor's installed browser/OS provider and distributes no voice model; provider terms and availability still vary. Trusted production identities, transactional operational storage, durable contact preferences, live telephony and validated financial models remain work in [the product production plan](product-production-plan.md) and [production readiness](production-readiness.md).

Official references: [free Community Cloud hosting](https://docs.streamlit.io/deploy/streamlit-community-cloud), [deployment fields and Python version](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [hosting Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [public sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).
