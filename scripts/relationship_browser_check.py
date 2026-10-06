"""Rehearse real local intake, source sync and scoped portals on isolated data."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from playwright.sync_api import expect, sync_playwright
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=["TEST-LOCAL-DEMO"], required=True)
    parser.parse_args()
    for port in (8002, 8503):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit("ISOLATED_CHECK_PORT_IN_USE")
    folder = ROOT / "output/cloud/relationship-browser"
    folder.mkdir(parents=True, exist_ok=True)
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "fresh localhost API and staff UI with temporary fictional SQLite records",
              "real_call_placed": False, "snowflake_written": False, "checks": [], "screenshots": []}
    current_check = "launch isolated servers"
    processes = []
    with tempfile.TemporaryDirectory(prefix="samvaad-relationship-") as workspace:
        tokens = {secrets.token_urlsafe(32): identity for identity in ("meera", "arjun", "local-runner")}
        environment = {**os.environ, "SAMVAAD_DB_PATH": str(Path(workspace) / "check.db"),
                       "SAMVAAD_BACKEND": "local", "SAMVAAD_DEMO_MODE": "true",
                       "SAMVAAD_API_TOKENS_JSON": json.dumps(tokens),
                       "SAMVAAD_RELATIONSHIP_API_ORIGIN": "http://127.0.0.1:8002",
                       "SAMVAAD_PUBLIC_BASE_URL": "http://127.0.0.1:8002",
                       "SAMVAAD_TELEPHONY_ENABLED": "false"}
        # Disable optional carrier settings inherited from a developer terminal.
        for name in list(environment):
            if name.startswith("SAMVAAD_TWILIO_") or name.startswith("TWILIO_"):
                environment.pop(name)

        def auth(identity, key=None):
            result = {"Authorization": "Bearer " + next(token for token, user in tokens.items() if user == identity)}
            if key:
                result["Idempotency-Key"] = key
            return result

        def api(method, path, identity="meera", key=None, payload=None):
            result = requests.request(method, "http://127.0.0.1:8002" + path,
                                      headers=auth(identity, key), json=payload, timeout=15)
            assert result.status_code == 200, "Authenticated relationship API operation failed"
            return result.json()

        def ready(url):
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                try:
                    if requests.get(url, timeout=2).status_code == 200:
                        return
                except requests.RequestException:
                    pass
                time.sleep(0.2)
            raise RuntimeError("Isolated server did not start")

        try:
            processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "webhook.main:create_app", "--factory",
                                               "--host", "127.0.0.1", "--port", "8002", "--no-access-log"],
                                              cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            ready("http://127.0.0.1:8002/health")
            processes.append(subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py",
                                               "--server.address", "127.0.0.1", "--server.port", "8503",
                                               "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                                              cwd=ROOT, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            ready("http://127.0.0.1:8503/_stcore/health")
            invite = api("POST", "/api/relationship/onboarding-invitations", key="browser-intake-0001")
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1050})
                applicant = context.new_page()
                applicant.goto("http://127.0.0.1:8002/portal/" + invite["token"], wait_until="domcontentloaded")
                current_check = "applicant form submission"
                applicant.get_by_role("textbox", name="Full name", exact=True).fill("Asha Relationship Demo")
                applicant.get_by_role("textbox", name="City", exact=True).fill("Pune")
                applicant.get_by_role("spinbutton", name="Monthly income (INR)", exact=True).fill("90000")
                applicant.get_by_role("textbox", name="Phone (E.164, optional)", exact=True).fill("+12025550100")
                applicant.get_by_role("checkbox", name="I permit service calls about this relationship.", exact=True).check()
                applicant.get_by_role("textbox", name="Permission reference / request note", exact=True).fill("Fictional intake rehearsal")
                applicant.get_by_role("button", name="Submit application for review", exact=True).click()
                expect(applicant.get_by_text("Application status: PENDING_REVIEW", exact=True)).to_be_visible()
                applicant.screenshot(path=str(folder / "applicant-submitted.png"), full_page=True)
                report["screenshots"].append("applicant-submitted.png")
                assert len(api("GET", "/api/customers")) == 20
                report["checks"].append("customer submits genuine scoped intake; no customer or loan created before review")

                current_check = "staff checklist and approval"
                staff = context.new_page()
                staff.goto("http://127.0.0.1:8503", wait_until="domcontentloaded")
                current_check = "staff relationship tab loads"
                staff.get_by_role("tab", name="Relationship hub", exact=True).wait_for(timeout=40000)
                expect(staff.get_by_role("tab")).to_have_count(6)
                staff.get_by_role("combobox", name="Demo operator", exact=True).click()
                staff.get_by_role("option", name=re.compile("Arjun")).click()
                current_check = "staff manager review checklist renders"
                expect(staff.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning", timeout=30000)
                staff.get_by_role("tab", name="Relationship hub", exact=True).click()
                expect(staff.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning", timeout=30000)
                staff.screenshot(path=str(folder / "manager-before-review.png"), full_page=True)
                (folder / "manager-before-review-visible.txt").write_text(staff.locator("body").inner_text(), encoding="utf-8")
                current_check = "staff identity checkbox"
                staff.get_by_text("Reviewer confirms identity review completed", exact=True).click()
                current_check = "staff document checkbox"
                staff.get_by_text("Reviewer confirms document review completed", exact=True).click()
                current_check = "staff approval note"
                staff.get_by_role("textbox", name="Officer review note", exact=True).fill("Reviewed fictional browser workflow documents")
                staff.get_by_role("button", name="Save onboarding decision", exact=True).click()
                current_check = "staff approval persists and displays confirmation"
                staff.get_by_text("Onboarding decision saved.", exact=False).wait_for(timeout=30000)
                application = next(row for row in api("GET", "/api/relationship/onboardings")
                                   if row["payload"]["full_name"] == "Asha Relationship Demo")
                customer_id = application["customer_id"]
                assert application["status"] == "APPROVED" and customer_id
                assert api("GET", "/api/customers/" + customer_id)["loans"] == []
                staff.screenshot(path=str(folder / "staff-approved.png"), full_page=True)
                report["screenshots"].append("staff-approved.png")
                report["checks"].append("manager checklist and approval create one durable customer, without invented credit")

                current_check = "source identity mapping and atomic import"
                api("POST", "/api/relationship/sync/customer-links", "arjun", "browser-map-0001",
                    {"source": "browser-lms", "source_record_id": "applicant-01", "customer_id": customer_id,
                     "note": "Reviewed fictional source identity"})
                now = datetime.now(timezone.utc)
                records = [
                    {"record_type": "loan", "source_record_id": "loan-01", "source_version": 1,
                     "customer_ref": "applicant-01", "product": "PERSONAL_LOAN", "principal": 500000,
                     "outstanding": 300000, "interest_rate": 14, "emi": 11000, "relationship_months": 36,
                     "current_dpd": 0, "status": "ACTIVE", "disbursed_on": "2023-01-01"},
                    {"record_type": "payment", "source_record_id": "payment-01", "source_version": 1,
                     "loan_ref": "loan-01", "due_date": now.date().isoformat(), "paid_date": now.date().isoformat(),
                     "amount_due": 11000, "amount_paid": 11000, "status": "PAID"},
                    {"record_type": "interaction", "source_record_id": "email-01", "source_version": 1,
                     "customer_ref": "applicant-01", "channel": "EMAIL", "text": "I would like to understand my loan options.",
                     "ts": now.isoformat()}]
                preview = api("POST", "/api/relationship/sync/preview", key="browser-sync-0001",
                              payload={"source": "browser-lms", "records": records})
                assert preview["status"] == "VALIDATED" and preview["errors"] == []
                assert api("GET", "/api/customers/" + customer_id)["loans"] == []
                applied = api("POST", "/api/relationship/sync/runs/" + preview["run_id"] + "/commit")
                assert applied["status"] == "COMMITTED"
                after = api("GET", "/api/customers/" + customer_id)
                assert len(after["loans"]) == len(after["payments"]) == len(after["interactions"]) == 1
                assert api("POST", "/api/relationship/sync/runs/" + preview["run_id"] + "/commit")["status"] == "COMMITTED"
                current_check = "synced customer picker refresh"
                staff.reload(wait_until="domcontentloaded")
                staff.get_by_role("combobox", name="Customer", exact=True).wait_for(timeout=30000)
                expect(staff.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning", timeout=30000)
                current_check = "synced customer picker options"
                staff.get_by_role("combobox", name="Customer", exact=True).click()
                staff.get_by_role("combobox", name="Customer", exact=True).fill("Asha Relationship Demo")
                (folder / "synced-picker-visible.txt").write_text(staff.locator("body").inner_text(), encoding="utf-8")
                staff.get_by_role("option", name=re.compile("Asha Relationship Demo")).click()
                current_check = "synced Customer 360 renders"
                expect(staff.locator('[data-testid="stApp"]')).to_have_attribute("data-test-script-state", "notRunning", timeout=30000)
                staff.get_by_role("tab", name="Customer 360", exact=True).click()
                staff.get_by_text("Asha Relationship Demo", exact=True).wait_for(timeout=30000)
                assert staff.locator('[data-testid="stException"]').count() == 0
                staff.screenshot(path=str(folder / "synced-customer360.png"), full_page=True)
                report["screenshots"].append("synced-customer360.png")
                report["checks"].append("reviewed external ID and validated atomic loan/payment/email import join the same Customer 360")

                current_check = "borrower request and contact withdrawal"
                customer_invite = api("POST", "/api/relationship/customers/" + customer_id + "/portal-invitations",
                                      key="browser-portal-0001")
                customer = context.new_page()
                customer.goto("http://127.0.0.1:8002/portal/" + customer_invite["token"], wait_until="domcontentloaded")
                customer.get_by_role("combobox", name="Request type", exact=True).select_option("HARDSHIP")
                customer.get_by_role("textbox", name="Subject", exact=True).fill("I lost my job")
                customer.get_by_role("textbox", name="Your message", exact=True).fill("I lost my job and need an officer to discuss repayment support.")
                customer.get_by_role("button", name="Send service request", exact=True).click()
                expect(customer.get_by_text("I lost my job", exact=True)).to_be_visible()
                relationship = api("GET", "/api/relationship/customers/" + customer_id)
                assert relationship["cases"][0]["category"] == "HARDSHIP"
                assert any("lost my job" in row["text"] for row in relationship["customer360"]["interactions"])
                assert relationship["customer360"]["metrics"]["hardship_flag"]
                assert relationship["customer360"]["current_decision"]["action_code"] not in {"TOPUP_PREAPPROVAL_CALL", "RETENTION_RATE_MATCH_CALL"}
                current_check = "customer contact withdrawal"
                customer.get_by_role("button", name="Stop all contact", exact=True).click()
                protected = api("GET", "/api/customers/" + customer_id)
                assert not protected["customer"]["consent_calls"] and not protected["customer"]["consent_marketing"]
                assert protected["current_decision"]["action_code"] == "NO_ACTION"
                customer.screenshot(path=str(folder / "customer-service-and-optout.png"), full_page=True)
                report["screenshots"].append("customer-service-and-optout.png")
                report["checks"].append("real customer form creates hardship evidence and service case; withdrawal blocks future contact")
                assert api("GET", "/api/relationship/outbox", "arjun")["counts"].get("PENDING", 0) > 0
                report["checks"].append("relationship changes queue ordered private analytics exports; no Snowflake write performed")

                current_check = "mobile scoped portal and invalid capability"
                mobile = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
                mobile.goto("http://127.0.0.1:8002/portal/" + customer_invite["token"], wait_until="domcontentloaded")
                assert mobile.locator("html").evaluate("element => element.scrollWidth <= innerWidth + 1")
                assert "Ananya" not in mobile.locator("body").inner_text()
                mobile.screenshot(path=str(folder / "customer-portal-mobile.png"), full_page=True)
                report["screenshots"].append("customer-portal-mobile.png")
                assert requests.get("http://127.0.0.1:8002/portal/unknown", timeout=10).status_code == 404
                report["checks"].append("mobile customer portal has no horizontal overflow, other-customer records or valid guessed capabilities")
                browser.close()
            report.update(status="PASSED", passed=len(report["checks"]))
        except Exception as error:
            # Browser/request exceptions can contain scoped URLs. Only expose
            # the checkpoint and exception class, never a capability or token.
            report.update(status="FAILED", checkpoint=current_check, error_type=type(error).__name__)
            if "staff" in locals() and not staff.is_closed():
                try:
                    staff.screenshot(path=str(folder / "failed-staff.png"), full_page=True)
                    (folder / "failed-staff-visible.txt").write_text(staff.locator("body").inner_text(), encoding="utf-8")
                except Exception:
                    pass
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    (folder / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
