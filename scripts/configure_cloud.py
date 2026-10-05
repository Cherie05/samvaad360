"""Set up non-secret staging metadata. No password arguments or cloud writes."""
import argparse
import json

from cloud.config import CloudError
from cloud.setup import configure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="Organization-account identifier from Snowsight")
    parser.add_argument("--user", required=True, help="Non-secret Snowflake login name")
    parser.add_argument("--warehouse", required=True, help="An existing warehouse visible to your role")
    parser.add_argument("--connection-name", default="samvaad_demo")
    parser.add_argument("--database", default="SAMVAAD_STAGING")
    parser.add_argument("--role", default=None)
    parser.add_argument("--auth", choices=["password-mfa", "externalbrowser"], default="password-mfa")
    parser.add_argument("--apply", action="store_true", help="Write local credential-free metadata; default only prints a plan")
    args = parser.parse_args(argv)
    try:
        result = configure(account=args.account, user=args.user, warehouse=args.warehouse,
                           auth=args.auth, name=args.connection_name, database=args.database,
                           role=args.role, apply=args.apply)
        print(json.dumps(result, indent=2))
        return 0
    except CloudError as exc:
        print(json.dumps({"status": "BLOCKED", "error": exc.code, "message": exc.message}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
