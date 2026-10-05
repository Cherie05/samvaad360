"""Build the six-file app release and an existing-app update script offline."""
import argparse
from pathlib import Path

from cloud.config import CloudConfig, identifier
from cloud.trial import APP, ROLE, package


def build(*, account, viewer, database="SAMVAAD_STAGING", warehouse="SAMVAAD_XS", output=None):
    config = CloudConfig("samvaad_hackathon", database, warehouse)
    folder, plan = package(config, account=account, user=viewer, output=output)
    # configure() called by package validates account/viewer and identifier()
    # validates SQL object names before any SQL literals are generated here.
    app_uri = f"snow://streamlit/{database.upper()}.APP.{APP}/versions/live/"
    sql = [f"USE ROLE {identifier(ROLE)}", "USE SECONDARY ROLES NONE",
           f"USE WAREHOUSE {identifier(warehouse)}", f"USE DATABASE {identifier(database)}", "USE SCHEMA APP",
           "EXECUTE IMMEDIATE $$\nDECLARE\n wrong_target EXCEPTION (-20001, 'Deployment account or role differs from the release target.');\nBEGIN\n"
           f" IF (UPPER(CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME()) <> '{account.upper()}' OR CURRENT_ROLE() <> '{ROLE}') THEN\n"
           "  RAISE wrong_target;\n END IF;\nEND;\n$$",
           f"DESCRIBE STREAMLIT {config.object('APP', APP)}"]
    for name in plan["files"]:
        local_uri = (folder / "app" / name).as_uri().replace("'", "''")
        sql.append(f"PUT '{local_uri}' '{app_uri}' AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
    sql.append(f"ALTER STREAMLIT {config.object('APP', APP)} COMMIT")
    sql.append(f"SELECT COUNT(*) AS CUSTOMERS FROM {config.object('CORE', 'CUSTOMER_360')}")
    path = folder / "04-update-existing-app.sql"
    path.write_text(";\n".join(sql) + ";\n", encoding="utf-8")
    return path, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--viewer", required=True)
    parser.add_argument("--database", default="SAMVAAD_STAGING")
    parser.add_argument("--warehouse", default="SAMVAAD_XS")
    parser.add_argument("--output", default="output/cloud/github")
    args = parser.parse_args()
    path, plan = build(**vars(args))
    print(f"Prepared {len(plan['files'])} allowlisted app files. Update script: {path}")


if __name__ == "__main__":
    main()
