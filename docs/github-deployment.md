# GitHub deployment to the hackathon account

The private repository is [Cherie05/samvaad360](https://github.com/Cherie05/samvaad360). The frontend and Python/Snowpark backend run inside the existing Snowflake Streamlit app; customer data stays in `SAMVAAD_STAGING`. GitHub provides source control, automated checks and code deployment. This setup does not publish a public borrower portal or deploy the local telephone worker.

## First connection

1. Fix and open the existing hosted app using the [startup repair](cloud-startup-repair.md). The simplified app environment specifies Streamlit 1.52.2 and inherits Snowflake's preinstalled Python and Snowpark.
2. In account `ZYLTUKM-HU63768`, open a Snowsight SQL worksheet, select `ACCOUNTADMIN`, and run [006_github_oidc.sql](../cloud/sql/006_github_oidc.sql). This creates the service user `SAMVAAD_GITHUB_DEPLOYER`, trusts short-lived GitHub tokens from this repository's **main branch**, and grants the existing dedicated synthetic app role. It does not store your personal password, create private keys, change billing, add account-wide roles or grant access to PUBLIC. If that username already exists or the account rejects OIDC, stop and inspect the specific setting; do not overwrite an existing user's authentication.
3. Open the repository **Settings > Secrets and variables > Actions > Variables** and configure:

| Variable | Value |
| --- | --- |
| `SNOWFLAKE_ACCOUNT` | `ZYLTUKM-HU63768` |
| `SAMVAAD_VIEWER` | `ARUNVPP24` |
| `SAMVAAD_DEPLOY_ENABLED` | `true` after the one-time account setup and hosted check |

No personal Snowflake password or MFA code goes into a GitHub secret. The official Snowflake action obtains a short-lived OIDC token for each deployment. Do not change the workflow's job to use a named GitHub environment without also updating the trusted OIDC subject: GitHub emits a different subject when a job targets an environment.

4. Under **Actions**, select **Test and deploy Samvaad 360 > Run workflow**, with branch **main**. Check that the test and deploy jobs pass, then reopen the hosted app. Publication output alone does not verify the browser. The account/role guard runs before file uploads.

## Subsequent releases

Push or merge changes to `main`: the Windows job runs the full automated suite, then the Ubuntu deployment job obtains its OIDC token, packages six allowlisted app files and updates the existing app's live files with Snowflake CLI. Pull requests run tests without cloud authentication. No schema/bootstrap SQL or synthetic fixture reload is executed by this workflow; demo reviews remain in their existing table. No CoCo/model calls are made during deployment.

The deployment script uses `PUT` and `ALTER STREAMLIT ... COMMIT`, preserving the app object. File uploads happen sequentially; a failed upload can leave a partially updated live version. This private synthetic demonstration does not promise zero downtime or atomic file releases. Retain the prior Git commit and redeploy it for recovery. Stop expanding the deployment to operational financial workflows until release/recovery and transaction controls are implemented.

The deployment variable initially stays `false` so the first source push cannot try an unconfigured Snowflake login. After configuration, the main-branch condition and short-lived identity are the deployment controls. GitHub Actions usage and Snowflake warehouse usage have their respective account budgets; the existing five-credit warehouse monitor does not cap AI or total account spending.

Files excluded from the repository include `.local`, `.venv`, output reports/audio, databases, credentials/private keys, model weights and the original PDF. The source and readable project documentation are versioned.

Official references: [Snowflake GitHub Action and OIDC setup](https://docs.snowflake.com/en/developer-guide/snowflake-cli/cicd/github-action), [Streamlit live files](https://docs.snowflake.com/en/sql-reference/sql/desc-streamlit), [committing a live version](https://docs.snowflake.com/en/sql-reference/sql/alter-streamlit). Native Snowsight Git synchronization is also supported, but the selected deployment path uses GitHub Actions and does not require a Snowflake Git API integration or a saved GitHub PAT in the Snowflake account.
