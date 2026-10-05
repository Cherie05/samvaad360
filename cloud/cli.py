"""Cloud preparation commands; plan by default and never provision compute."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cloud.capabilities import coco_report, metadata_report, offline_report
from cloud.config import CloudError, WORKSPACE, connect, identifier, read_config
from cloud.fixtures import DEFAULT_REFERENCE, build_bundle, canonical, load_fixture, read_bundle
from cloud.sql_assets import render, statements


def parser():
    result = argparse.ArgumentParser(description="Samvaad cloud preparation. The application backend remains local.")
    result.add_argument("--config", default=None, help="Non-secret cloud TOML configuration")
    commands = result.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Inspect local prerequisites; optionally read account metadata")
    doctor.add_argument("--connect", action="store_true", help="Use the named connection for metadata-only queries")
    doctor.add_argument("--output", default=None, help="Write the credential-free capability report to JSON")
    deploy = commands.add_parser("deploy", help="Render analytics DDL; optionally apply it")
    deploy.add_argument("--apply", action="store_true", help="Create analytics schemas/tables/views using the configured account")
    deploy.add_argument("--include-search", action="store_true", help="Also create scheduled Cortex Search, which incurs credits")
    deploy.add_argument("--output", default=str(WORKSPACE / "output" / "cloud" / "deploy.sql"))
    export = commands.add_parser("export", help="Export deterministic synthetic fixtures without a cloud account")
    export.add_argument("--customers", type=int, default=20)
    export.add_argument("--reference", default=DEFAULT_REFERENCE)
    export.add_argument("--output", default=str(WORKSPACE / "output" / "cloud" / "fixtures.json"))
    load = commands.add_parser("load", help="Validate a fixture bundle; optionally bootstrap empty cloud raw tables")
    load.add_argument("--fixture", default=str(WORKSPACE / "output" / "cloud" / "fixtures.json"))
    load.add_argument("--apply", action="store_true")
    enrich = commands.add_parser("enrich", help="Render bounded Cortex SQL; optionally run it")
    enrich.add_argument("--limit", type=int, default=5)
    enrich.add_argument("--apply", action="store_true", help="Run up to --limit AI enrichments, which incur credits")
    enrich.add_argument("--output", default=str(WORKSPACE / "output" / "cloud" / "enrichment.sql"))
    coco = commands.add_parser("coco", help="Verify installed CoCo help/version, optionally its account/model authentication")
    coco.add_argument("--run-smoke", action="store_true", help="Make one bounded CoCo model request, which incurs credits")
    coco.add_argument("--output", default=None, help="Write the credential-free CoCo capability report to JSON")
    for command in commands.choices.values():
        command.add_argument("--config", default=argparse.SUPPRESS, help="Non-secret cloud TOML configuration")
    for name in ("doctor", "deploy", "load", "enrich"):
        commands.choices[name].add_argument("--prompt-password", action="store_true", help="Prompt locally for native-login MFA; password is not saved or accepted in arguments")
    return result


def _print(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _write(path, text):
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return str(target)


def _select_existing_warehouse(cursor, config):
    config.require_warehouse()
    cursor.execute("SHOW WAREHOUSES")
    rows = cursor.fetchall()
    columns = [column[0].lower() for column in cursor.description]
    index = columns.index("name")
    if not any(str(row[index]).upper() == config.warehouse.upper() for row in rows):
        raise CloudError("WAREHOUSE_NOT_VISIBLE", "The configured existing warehouse is not visible to this connection's role.")
    cursor.execute("USE WAREHOUSE " + identifier(config.warehouse))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        config = read_config(args.config)
        if args.command == "doctor":
            report = (metadata_report(config, prompt_password=True) if args.prompt_password else metadata_report(config)) if args.connect else offline_report(config)
            if args.output:
                _write(args.output, json.dumps(report, indent=2) + "\n")
            _print(report)
            ready = report["connector_installed"] and report["configured_connection"] and report["named_connection_found"] and report["existing_warehouse_selected"]
            if args.connect:
                ready = ready and report["cloud_metadata_checked"] and report.get("selected_warehouse_visible", False)
            return 0 if ready else 2
        if args.command == "coco":
            report = coco_report(config, run_smoke=args.run_smoke)
            if args.output:
                _write(args.output, json.dumps(report, indent=2) + "\n")
            _print(report)
            return 0 if report["model_smoke_verified"] else 2
        if args.command == "export":
            bundle = build_bundle(args.customers, args.reference)
            output = _write(args.output, canonical(bundle) + "\n")
            _print({"status": "EXPORTED", "synthetic": True, "path": output, "counts": bundle["counts"], "sha256": bundle["sha256"]})
            return 0
        if args.command == "load":
            bundle = read_bundle(args.fixture)
            if not args.apply:
                _print({"status": "VALIDATED_PLAN", "counts": bundle["counts"], "sha256": bundle["sha256"], "cloud_modified": False, "next": "Use load --apply with a configured account and empty analytics tables."})
                return 0
            config.require_warehouse()
            with (connect(config, prompt_password=True) if args.prompt_password else connect(config)) as connection:
                with connection.cursor() as cursor:
                    _select_existing_warehouse(cursor, config)
                _print(load_fixture(connection, config, bundle))
            return 0
        assets = ["schema", "views"] if args.command == "deploy" else ["enrichment"]
        if args.command == "deploy" and args.include_search:
            assets.append("search")
        sql = "\n\n".join(render(asset, config, limit=getattr(args, "limit", 5)) for asset in assets)
        output = _write(args.output, sql)
        if not args.apply:
            _print({"status": "SQL_PREPARED", "path": output, "assets": assets, "cloud_modified": False, "cloud_backend_implemented": False})
            return 0
        config.require_warehouse()
        with (connect(config, prompt_password=True) if args.prompt_password else connect(config)) as connection:
            with connection.cursor() as cursor:
                _select_existing_warehouse(cursor, config)
                for statement in statements(sql):
                    cursor.execute(statement)
                if args.command == "enrich":
                    cursor.execute(f"SELECT COUNT(*),COUNT_IF(COALESCE(INTENT_RESULT:error::VARCHAR,'') NOT IN ('','null') OR COALESCE(SENTIMENT_RESULT:error::VARCHAR,'') NOT IN ('','null') OR COALESCE(ENTITY_RESULT:error::VARCHAR,'') NOT IN ('','null') OR INTENT_RESULT IS NULL OR SENTIMENT_RESULT IS NULL OR ENTITY_RESULT IS NULL) FROM {config.object('AI','INTERACTION_SIGNALS')} WHERE PROVIDER='snowflake-cortex-v1'")
                    count, errors = cursor.fetchone()
                    _print({"status": "ENRICHED_REVIEW_REQUIRED", "total_cortex_rows": count, "error_rows": errors or 0, "max_rows_this_run": args.limit, "automated_decisions_enabled": False})
                    return 0 if not errors else 2
        _print({"status": "ANALYTICS_ASSETS_APPLIED", "assets": assets, "workflow_backend": "NOT_DEPLOYED", "warehouse_created": False})
        return 0
    except CloudError as exc:
        _print({"status": "BLOCKED", "error": exc.code, "message": exc.message, "cloud_deployed": False})
        return 2
    except Exception as exc:
        # Provider exceptions may contain endpoint details, SQL, or secrets.
        _print({"status": "FAILED", "error_type": type(exc).__name__, "error_code": getattr(exc, "errno", None), "message": "Cloud operation failed. Review account privileges, schema, region, and private connector diagnostics. No provider exception or credentials were printed."})
        return 2


if __name__ == "__main__":
    sys.exit(main())
