# Hosted app package startup failure

The owner reported that `SAMVAAD360` fails before Python startup with:

> SQL compilation error: Cannot create a Python function with the specified packages.

The warehouse, database, synthetic fixture import and app publication succeeded. A published app is not yet a working hosted website. The actual account catalog contains Streamlit 1.52.2; its Python 3.11 library resolver successfully resolved Streamlit 1.52.2 and Snowpark 1.55.0. That resolver does not exercise the internal hosted Streamlit launcher. The owner also tried the simplified `environment.yml` below and reported the same hosted error. The root cause remains unconfirmed.

```yaml
name: samvaad-hackathon
channels:
  - snowflake
dependencies:
  - streamlit=1.52.2
```

The [GitHub deployment](github-deployment.md) connection is now verified. [The actual run](https://github.com/Cherie05/samvaad360/actions/runs/37330489632) passed 210 tests, authenticated with a short-lived OIDC token, published `SAMVAAD_RUNTIME_CHECK` and confirmed the 20-customer count. The owner opened this default-environment app and reported the same compilation error with the additional detail **`Packages not found: python==3.11`**. It has no `environment.yml` or customer-data queries. This reproduces the failure independently of Samvaad's custom packages and application code; it does not yet identify the account/runtime cause.

The manual **Diagnose Snowflake hosted runtime** GitHub workflow now inspects the two app descriptors, the Python package catalog and temporary Python 3.11/3.10 UDFs. Its Python 3.11 library probe uses Streamlit/Snowpark in `PACKAGES` and specifies Python separately with `RUNTIME_VERSION`, following the documented UDF interface. It changes no customer tables, application files, grants, package policies or billing settings. Temporary functions expire with their CLI sessions. Findings appear as `RUNTIME_DIAGNOSIS` in the workflow log. An ordinary Python UDF result is distinct from actual hosted app startup.

[The successful runtime diagnosis](https://github.com/Cherie05/samvaad360/actions/runs/37334368737) verified Python **3.11.15**, Streamlit **1.52.2** and Snowpark **1.55.0** by actually executing a temporary UDF. Python 3.10.20 also executed successfully. Both apps use the warehouse runtime; the blank diagnostic has empty user packages. The catalog lists complete Python patch versions rather than a bare `3.11` entry. The default managed launcher still fails in the owner's browser, so a fully specified Python patch is being tested as a workaround; this is an inference, not a confirmed root cause.

The workflow's optional `publish_pinned_check` input publishes a separate `SAMVAAD_PINNED_RUNTIME_CHECK` app with Python 3.11.15, Streamlit 1.52.2 and Snowpark 1.55.0 in its environment. It preserves both the original blank check and `SAMVAAD360`. Only an actual browser result can establish whether the explicit pin fixes hosted startup. The first diagnosis attempt stopped on nested CLI result parsing; the parser was corrected and the successful run linked above supersedes it.

The owner subsequently confirmed that **`SAMVAAD_PINNED_RUNTIME_CHECK` opens** after [its publication](https://github.com/Cherie05/samvaad360/actions/runs/37335059500). This is the first successful hosted startup observation. The full environment above is now applied to the main app source, with main-app publication/browser rehearsal still pending. The owner has not yet supplied the diagnostic's displayed version JSON.

Two later main-app uploads failed with **099108: Live version is not found**, before the first `PUT`; the previous release remains committed. The deployment now inspects the live file location before and after an app update and restores it from the committed version only for that exact missing-version error. Other errors stop deployment. Existing live edits are preserved by the inspection; no abort, app replacement or data reload is used. A real GitHub run must still verify this recovery path.

The first OIDC login used GitHub's older name-only subject and failed. The owner completed the scoped correction to this new repository's immutable owner/repository identity; the retried deployment passed. No further private password prompt is currently required. The earlier diagnostic connections were closed; no customer data or hosted app files were modified by those helper attempts. A Windows GET backup-path failure was corrected in the helper before source publication. Python is the runtime argument of the package resolver, not a package to include in its PACKAGES specification.

## Private diagnostic and targeted repair

Open the **Samvaad 360 - Private Cloud Environment Repair** terminal that the developer launched. Enter the password and MFA code only in that terminal. Credentials from the earlier setup were not saved. After **Package diagnostics saved**, leave the terminal open and inform the developer. Its authenticated connection closes after repair, exit or 15 minutes of waiting after diagnostics.

If that window is unavailable, start it yourself from this workspace:

```powershell
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File .\scripts\repair_cloud_runtime.ps1
```

The helper verifies the account, login and dedicated app role, reads `DESCRIBE STREAMLIT` and `INFORMATION_SCHEMA.PACKAGES`, and calls Snowflake's package resolver with the original and unpinned package specifications. It saves a credential-free report at `output/cloud/runtime-repair/result.json`. Provider messages are classified rather than printed; numeric error codes are retained.

After examining that report, the developer can select a Streamlit/Snowpark library combination present in the catalog. The helper accepts only this bounded environment operation or an exit request, validates Streamlit against the documented warehouse versions, and resolves the libraries before mutation. The simplified environment pins Streamlit and inherits Python/Snowpark from the managed app runtime. It backs up the live `environment.yml`, uploads only its replacement to the existing app's live files, verifies the downloaded read-back, and commits the app version. It does not create or replace the app object, reload customer data, change review rows, grant privileges, alter package policies, accept terms or change billing.

The version backup remains in `output/cloud/runtime-repair/before/environment.yml`. Package resolution does not prove hosted startup: refresh **Projects > Streamlit > SAMVAAD360** using role `SAMVAAD_HACKATHON`, then complete the four-tab rehearsal in [the cloud setup guide](hackathon-cloud-setup.md). Actual Cortex and CoCo checks remain separate.

If the account explicitly reports missing package terms or enablement, the owner must inspect the relevant account setting privately. Do not infer this cause from the generic compilation error. The helper does not accept agreements or disable account policies.

Official references: [package management and preinstalled libraries](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management), [package resolver](https://docs.snowflake.com/en/sql-reference/functions/system_resolve_python_packages), [live app files](https://docs.snowflake.com/en/sql-reference/sql/desc-streamlit), [committing the live version](https://docs.snowflake.com/en/sql-reference/sql/alter-streamlit).
