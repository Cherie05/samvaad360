"""Actual bounded reads from the dedicated Snowflake public backend."""
import json
import tomllib
from datetime import datetime, timezone

from cloud.config import WORKSPACE
from cloud.runtime_repair import safe_error
from public_app.repository import connect_reader, ReviewSandbox, DemoError


def main():
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "status": "STARTED",
              "external_delivery": False, "financial_execution": False, "ai_calls": 0}
    reader = None
    try:
        values = tomllib.loads((WORKSPACE / ".local/public-cloud/secrets.toml").read_text(encoding="utf-8"))["snowflake"]
        reader = connect_reader(values)
        report["customers"] = len(reader.customers())
        report["actions"] = {cid: reader.customer360(cid)["decision"]["action_code"] for cid in ["C0001", "C0002", "C0003", "C0004"]}
        expected = {"C0001": "HARDSHIP_RESTRUCTURE_CALL", "C0002": "RETENTION_RATE_MATCH_CALL",
                    "C0003": "TOPUP_PREAPPROVAL_CALL", "C0004": "NO_ACTION"}
        if report["customers"] != 20 or report["actions"] != expected:
            raise DemoError("Cloud public scenarios did not match the approved synthetic fixture.")
        result = reader.answer("C0003", "Why is the next action recommended?")
        report["answer_evidence_count"] = len(result["evidence"])
        first, other = ReviewSandbox([], reader), ReviewSandbox([], reader)
        rid = first.request("C0003")
        first.review(rid, "APPROVED_IN_SIMULATION", "Actual cloud read; isolated simulation")
        report["review_simulation"] = first.state[0]["status"]
        report["other_visit_isolated"] = other.state == []
        report["status"] = "PASSED"
    except Exception as error:
        report.update(status="FAILED", error=safe_error(error))
    finally:
        if reader is not None:
            reader.session.connection.close()
        path = WORKSPACE / "output/cloud/public-runtime-check.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
