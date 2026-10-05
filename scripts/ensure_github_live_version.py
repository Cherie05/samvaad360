"""Restore a missing writable app version without discarding existing edits."""
import json
import os
from pathlib import Path

from cloud.config import CloudConfig
from cloud.runtime_repair import download_uri
from scripts.diagnose_github_runtime import query


def ensure(account, config, execute=query):
    result = execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT, CURRENT_ROLE() AS ROLE")
    if not result.get("ok") or len(result.get("rows", [])) != 1:
        raise ValueError("IDENTITY_CHECK_FAILED")
    identity = {k.upper(): v for k, v in result["rows"][0].items()}
    if str(identity.get("ACCOUNT", "")).upper() != account.upper() or identity.get("ROLE") != "SAMVAAD_HACKATHON":
        raise ValueError("WRONG_ACCOUNT_OR_ROLE")
    uri = f"snow://streamlit/{config.database.upper()}.APP.SAMVAAD360/versions/live/"
    folder = Path("output/cloud/live-probe")
    folder.mkdir(parents=True, exist_ok=True)
    inspect = f"GET '{uri}environment.yml' '{download_uri(folder)}'"
    current = execute(inspect)
    if current.get("ok"):
        return {"ready": True, "created": False}
    if "099108" not in current.get("codes", []):
        raise ValueError("LIVE_VERSION_INSPECTION_FAILED " + json.dumps(current))
    result = execute("ALTER STREAMLIT " + config.object("APP", "SAMVAAD360") + " ADD LIVE VERSION FROM LAST")
    if not result.get("ok") or not execute(inspect).get("ok"):
        raise ValueError("LIVE_VERSION_RECOVERY_FAILED " + json.dumps(result))
    return {"ready": True, "created": True}


def main():
    config = CloudConfig("github_oidc", os.environ["SNOWFLAKE_DATABASE"], os.environ["SNOWFLAKE_WAREHOUSE"])
    print("LIVE_VERSION_READY " + json.dumps(ensure(os.environ["SNOWFLAKE_ACCOUNT"], config)))


if __name__ == "__main__":
    main()
