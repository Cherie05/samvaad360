# Public website with a Snowflake backend

The public lender prototype uses Streamlit Community Cloud for its browser UI and Python backend, and this hackathon account for live analytical reads. Community Cloud hosting is free; Snowflake warehouse queries consume account credits. The existing private Snowsight app remains the operator demonstration.

**Verified public website:** [samvaad360.streamlit.app](https://samvaad360.streamlit.app/). **Public source:** [Cherie05/samvaad360](https://github.com/Cherie05/samvaad360). On 5 October 2026, all six checks passed in fresh anonymous browser contexts with the live Snowflake source, evidence answers, isolated review workflow and mobile layout. GitHub passed 239 tests and deployed the private operator app. The deployment steps below also serve as recovery instructions.

| Component | Public deployment |
| --- | --- |
| Frontend and Python backend | `public_app/streamlit_app.py` on Streamlit Community Cloud, Python 3.11 |
| Database | `SAMVAAD_STAGING.PUBLIC_DEMO` in account `ZYLTUKM-HU63768` |
| Server identity | `SAMVAAD_PUBLIC_SERVICE`, authenticated with an encrypted RSA key stored only in hosting Secrets |
| Permissions | `SAMVAAD_PUBLIC_READONLY`: database/schema/warehouse usage and SELECT on four approved fictional snapshots |
| Customer journeys | 20 fictional customers; hardship, retention, top-up and DND examples |
| Public review workflow | Per-visit simulation, without database writes or staff identity |
| Evidence answers | Deterministic summaries with transcript citations; no public Cortex calls |
| Backup when the trial is unavailable | Checked fictional JSON bundle, prominently labelled offline; never described as a live Snowflake response |

The public adapter admits seven fixed, bounded read queries: four customer-scoped patterns and three portfolio batches. Building the portfolio uses four reads total, avoiding a separate query chain for every customer. It cannot read the private review queue, update financial terms or invoke AI. The public snapshots isolate this demo from future changes to the private RAW dataset. Do not replace them with customer data. Read caching lasts five minutes; the existing X-Small warehouse auto-suspends after 60 seconds and has a five-credit daily warehouse monitor. That monitor is not an account-wide spending guarantee.

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
7. Copy the actual assigned `https://...streamlit.app` URL. An optional subdomain is a suggestion until deployment confirms it. Open the link in an incognito window and confirm the sidebar says **Data source: Snowflake** and the four tabs appear.

If the sidebar says **offline synthetic snapshot**, the website is functioning in backup mode; live Snowflake connectivity has not passed for that hosting instance. Check its private logs/settings rather than presenting the fallback as a cloud database result.

## Verification and ongoing updates

The local and GitHub gates passed 239 tests. Real service-key authentication retrieved 20 customers and verified the four hero decisions. Six browser checks passed against localhost, then against the public host, with actual Snowflake reads: four tabs, top-up review simulation, visitor isolation, evidence scope, DND restriction and mobile layout.

After deployment, run this independent check with the actual URL:

```powershell
.\.venv\Scripts\python.exe -m scripts.public_browser_check --url 'https://samvaad360.streamlit.app/'
```

The browser uses fresh contexts without owner cookies or hosting credentials. It checks the application iframe inside the Community Cloud wrapper, expects a live Snowflake source, tests the workflow, and records success only after all checks pass. Hosted reports/screenshots are ignored under `output/cloud/public-browser/hosted/`; local evidence remains in the parent folder. The explicit `--allow-snapshot` option can check backup-mode UI; its report still records the actual source and cannot mark that backend as live.

Community Cloud redeploys source changes from GitHub. Dependencies are pinned in `public_app/requirements.txt`; root `.streamlit/config.toml` provides the theme. The existing GitHub Actions workflow also tests the full application and releases the private Snowflake operator app with OIDC. It never uploads the public reader's private key.

## Submission and production limits

The participant portal supplied by the owner lists **6 October 2026, 11:59 PM IST** as the submission deadline. It requires a public source repository, deployed URL, brief, CoCo CLI video and organizer-template PDF deck. Publishing the website does not automatically make the source public or supply the CoCo/video/deck evidence.

This is a synthetic hackathon prototype. Trusted production identities, transactional operational storage, live telephony and validated financial models remain separate work in [production readiness](production-readiness.md).

Official references: [free Community Cloud hosting](https://docs.streamlit.io/deploy/streamlit-community-cloud), [deployment fields and Python version](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [hosting Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management), [public sharing](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).
