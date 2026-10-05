# Warehouse-runtime advisory review

Reviewed 5 October 2026, IST. The cloud demo targets Snowflake's documented warehouse-runtime Streamlit 1.52.2. A package-version scan reports four raw entries representing **two distinct advisories**. The findings remain recorded; this is not a clean dependency scan or a production approval. The existing local website still runs patched Streamlit 1.65.0; its 101-package scan has zero reported advisories.

| Advisory | Published scope and fix | Applicability to this scoped demo |
| --- | --- | --- |
| CVE-2026-33682 / GHSA-7p48-42j8-8846 | Windows-only filesystem/UNC request handling, fixed in 1.54.0 | Snowflake hosting is Linux, so the vendor's Windows prerequisite is absent. The isolated 1.52.2 installation was used for offline AppTests, without starting a Windows HTTP server. Never use this older version for a Windows web server. |
| CVE-2026-10804 / GHSA-vqwp-45wm-r9r5 | Cached-data hashing collisions, including large-data sampling and PIL palette handling; fixed in 1.53.1 | The shipped demo uses fresh bound Snowpark queries, no `st.cache_data` / `st.cache_resource` / `st.cache`, no PIL processing, no uploads or third-party components. No cache result is used to authorize viewers or financial actions. These source-level facts reduce the identified attack surface; they do not patch the underlying library or certify Snowflake's internals. |

The Windows scope comes directly from the [Streamlit maintainer advisory](https://github.com/streamlit/streamlit/security/advisories/GHSA-7p48-42j8-8846). Cache behavior is described in the [upstream fix](https://github.com/streamlit/streamlit/pull/15397) and [reviewed advisory](https://github.com/advisories/GHSA-vqwp-45wm-r9r5). Hosting/platform and version availability come from [Snowflake runtime documentation](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments) and [dependency documentation](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management).

The deployment decision is limited to a private, one-viewer, fictional-data hackathon demo without financial execution. No public app grant is created. The review queue is a demonstration and cannot approve loans, send links or make calls. Allowlisted identity and fixture validation are independent of Streamlit's cache. Generated answers use a plain-text renderer. Source packages and their manifest remain reviewable.

For production, use a supported runtime with a patched Streamlit release and a complete installed dependency/binary audit, or obtain an account/platform security determination for the managed warehouse build. Do not claim that upstream package advisories are fixed merely because the app avoids their identified surface. Enabling caches, image processing, uploads, public sharing or additional viewers requires a new review.

Evidence: `output/cloud/warehouse-package-advisories.json`, `output/cloud/warehouse-compatibility-tests.xml`, and the six-file deployment manifest in `output/cloud/trial/plan.json`.

