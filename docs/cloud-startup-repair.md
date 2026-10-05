# Hosted app package startup failure

The owner reported that `SAMVAAD360` fails before Python startup with:

> SQL compilation error: Cannot create a Python function with the specified packages.

The warehouse, database, synthetic fixture import and app publication succeeded. A published app is not yet a working hosted website. The root cause remains unconfirmed until the actual account's package resolver and app metadata are inspected.

## Private diagnostic and targeted repair

Open the **Samvaad 360 - Private Cloud Environment Repair** terminal that the developer launched. Enter the password and MFA code only in that terminal. Credentials from the earlier setup were not saved. After **Package diagnostics saved**, leave the terminal open and inform the developer. Its authenticated connection closes after repair, exit or 15 minutes of waiting after diagnostics.

If that window is unavailable, start it yourself from this workspace:

```powershell
powershell.exe -NoProfile -NoExit -ExecutionPolicy Bypass -File .\scripts\repair_cloud_runtime.ps1
```

The helper verifies the account, login and dedicated app role, reads `DESCRIBE STREAMLIT` and `INFORMATION_SCHEMA.PACKAGES`, and calls Snowflake's package resolver with the original and unpinned package specifications. It saves a credential-free report at `output/cloud/runtime-repair/result.json`. Provider messages are classified rather than printed; numeric error codes are retained.

After examining that report, the developer can select an exact Streamlit/Snowpark combination present in the catalog. The helper accepts only this bounded environment operation or an exit request, validates Streamlit against the documented warehouse versions, and resolves the selected combination before mutation. It backs up the live `environment.yml`, uploads only its replacement to the existing app's live files and commits the app version. It does not create or replace the app object, reload customer data, change review rows, grant privileges, alter package policies, accept terms or change billing.

The version backup remains in `output/cloud/runtime-repair/before/environment.yml`. Package resolution does not prove hosted startup: refresh **Projects > Streamlit > SAMVAAD360** using role `SAMVAAD_HACKATHON`, then complete the four-tab rehearsal in [the cloud setup guide](hackathon-cloud-setup.md). Actual Cortex and CoCo checks remain separate.

If the account explicitly reports missing package terms or enablement, the owner must inspect the relevant account setting privately. Do not infer this cause from the generic compilation error. The helper does not accept agreements or disable account policies.

Official references: [package management and preinstalled libraries](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management), [package resolver](https://docs.snowflake.com/en/sql-reference/functions/system_resolve_python_packages), [live app files](https://docs.snowflake.com/en/sql-reference/sql/desc-streamlit), [committing the live version](https://docs.snowflake.com/en/sql-reference/sql/alter-streamlit).
