# CoCo local automation scaffold

Project skills live in `.cortex/skills/`; use CoCo's `/skill list` and invoke `samvaad-generate`, `samvaad-approved-runner`, or `samvaad-reset` after installing/configuring CoCo separately. No Snowflake connection is needed to run the Python commands locally; CoCo itself still requires its own enabled account/session.

The project `PreToolUse` hook receives structured JSON and checks explicit action IDs, bypass flags, manual approvals, and live contact windows. Activate the project virtual environment before launching CoCo so `python .cortex/hooks/guard_actions.py` resolves the project interpreter. Commands use forward-slash interpreter paths if needed on Windows. The hook is supplementary and cannot sandbox arbitrary shell code; the application service enforces policy for every execution route.

This is a prepared integration scaffold. Running Python CLI commands alone does not demonstrate a CoCo execution. Verify skill discovery and actual hook invocation in an installed CoCo session before claiming CoCo integration is complete.

Configuration follows [Snowflake's CoCo extensibility documentation](https://docs.snowflake.com/en/user-guide/cortex-code/extensibility). All outbound delivery remains disabled in the local build. Cloud identity, live channels, Cortex AI, and deployed CoCo execution remain separate migration tasks.
