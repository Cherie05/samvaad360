"""One-time private setup of the reviewed GitHub deployment service user."""
import json
from pathlib import Path

from cloud.config import CloudError, WORKSPACE
from cloud.runtime_repair import safe_error
from cloud.sql_assets import statements
from cloud.trial import authenticate, _named_rows


def main():
    target = WORKSPACE / "output/cloud/github-connection.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "WAITING_FOR_PRIVATE_LOGIN", "account": "ZYLTUKM-HU63768",
              "github_repository": "Cherie05/samvaad360", "service_user": "SAMVAAD_GITHUB_DEPLOYER",
              "trusted_subject": "repo:Cherie05/samvaad360:ref:refs/heads/main",
              "role": "SAMVAAD_HACKATHON", "credentials_saved": False, "billing_changed": False}
    def save():
        target.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    save()
    try:
        print("Connects the private GitHub repository to the existing synthetic Snowflake app.\nEnter password/MFA only here. They are hidden and not saved.", flush=True)
        with authenticate("ZYLTUKM-HU63768", "ARUNVPP24") as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME(), CURRENT_USER(), CURRENT_ROLE()")
                account, user, role = cursor.fetchone()
                if str(account).upper() != "ZYLTUKM-HU63768" or user != "ARUNVPP24" or role != "ACCOUNTADMIN":
                    raise CloudError("WRONG_ACCOUNT_USER_OR_ROLE", "This one-time connection needs the expected account owner; no changes were made.")
                users = _named_rows(cursor, "SHOW USERS LIKE 'SAMVAAD_GITHUB_DEPLOYER'")
                if any(row.get("name") == "SAMVAAD_GITHUB_DEPLOYER" for row in users):
                    raise CloudError("DEPLOY_USER_ALREADY_EXISTS", "The deployment user already exists. Its authentication was preserved; test the existing connection before changing it.")
                report["status"] = "CREATING_SCOPED_GITHUB_CONNECTION"
                save()
                for statement in statements((WORKSPACE / "cloud/sql/006_github_oidc.sql").read_text(encoding="utf-8")):
                    cursor.execute(statement)
        report["status"] = "GITHUB_SERVICE_USER_CONFIGURED"
        report["next"] = "The developer will enable the GitHub workflow and verify its short-lived Snowflake login."
        save()
        print("GitHub connection setup completed. Return to the chat; no SQL or secrets need to be copied.", flush=True)
        return 0
    except Exception as error:
        report.update(status="GITHUB_CONNECTION_INCOMPLETE", error=safe_error(error))
        save()
        print("Setup did not finish. Share only the visible status/error code; never credentials.", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
