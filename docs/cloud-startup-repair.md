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

The selected next path is [GitHub deployment](github-deployment.md) with short-lived authentication, then an unpinned default-runtime diagnostic app. The one-time service-user SQL is pending. No further private password prompt is currently required; the earlier diagnostic connections were closed. No customer data or hosted app files were modified by those helper attempts. A Windows GET backup-path failure was corrected in the helper before source publication. Python is the runtime argument of the package resolver, not a package to include in its PACKAGES specification.

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
