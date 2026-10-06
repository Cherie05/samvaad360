"""HTTP-boundary CRM acceptance: persistent operations and scoped borrower forms.

Every application uses an isolated SQLite file and disabled telephone settings.
These tests never contact Snowflake, an identity provider, or a carrier.
"""
import json
import re
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from samvaad.service import LocalService, timestamp
from webhook.main import create_app


TOKENS = {
    "private-isolated-analyst-token": "meera",
    "private-isolated-manager-token": "arjun",
    "private-isolated-credit-token": "kavya",
    "private-isolated-admin-token": "demo-admin",
    "private-isolated-runner-token": "local-runner",
}


@pytest.fixture
def api(service, monkeypatch):
    monkeypatch.delenv("SAMVAAD_TELEPHONY_ENABLED", raising=False)
    app = create_app(service, token_map=TOKENS)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def headers(role="analyst", key=None):
    token = next(token for token in TOKENS if f"-{role}-" in token)
    result = {"Authorization": "Bearer " + token}
    if key:
        result["Idempotency-Key"] = key
    return result


def profile(**changes):
    return {"full_name": "Fictional Portal Applicant", "city": "Chennai", "segment": "SALARIED",
            "monthly_income": 80000, "preferred_language": "English", "phone": "+15005550009",
            "email": "portal-fixture@example.invalid", "consent_calls": True,
            "consent_marketing": True, "dnd": False, "consent_reference": "Requested fictional pilot relationship contact", **changes}


def post(api, route, body, role="analyst", key=None):
    return api.post(route, json=body, headers=headers(role, key))


def invite(api, cid="C0002", key="customer-invite-0001"):
    result = api.post(f"/api/relationship/customers/{cid}/portal-invitations", headers=headers(key=key))
    assert result.status_code == 200, result.text
    return result.json()


def portal_event(page):
    match = re.search(r'name="event_id" value="(portal:[0-9a-f]{32})"', page.text)
    assert match, page.text[:200]
    return match.group(1)


def submit_form(api, token, payload, event=None):
    event = event or portal_event(api.get(f"/portal/{token}"))
    data = {"event_id": event, **payload}
    return api.post(f"/portal/{token}/submit", data=data)


def staff_onboard(api, **changes):
    request = post(api, "/api/relationship/onboardings", {**profile(**changes), "identity_review": True, "document_review": True}, key="staff-onboarding-0001")
    assert request.status_code == 200, request.text
    oid = request.json()["onboarding_id"]
    approved = post(api, f"/api/relationship/onboardings/{oid}/review", {"decision": "APPROVE", "note": "Reviewed fictional identity and documents"}, role="manager")
    assert approved.status_code == 200, approved.text
    return approved.json()["customer_id"]


def source_loan(**changes):
    return {"record_type": "loan", "source_record_id": "loan-001", "source_version": 1,
            "customer_ref": "external-customer-001", "product": "PERSONAL_LOAN", "principal": 400000,
            "outstanding": 280000, "interest_rate": 14, "emi": 10000,
            "relationship_months": 36, "current_dpd": 0, "status": "ACTIVE", "disbursed_on": "2023-01-01", **changes}


def source_payment():
    return {"record_type": "payment", "source_record_id": "payment-001", "source_version": 1,
            "loan_ref": "loan-001", "due_date": "2026-10-01", "paid_date": "2026-10-01",
            "amount_due": 10000, "amount_paid": 10000, "status": "PAID"}


def source_interaction(**changes):
    return {"record_type": "interaction", "source_record_id": "call-001", "source_version": 1,
            "customer_ref": "external-customer-001", "channel": "CALL_IN", "ts": timestamp(),
            "text": "I am unhappy about this high interest rate. I want foreclosure and balance transfer. Another bank offered 11 percent.", **changes}


def source_link(api, cid):
    result = post(api, "/api/relationship/sync/customer-links", {"source": "core_lms", "source_record_id": "external-customer-001",
                  "customer_id": cid, "note": "Reviewed source identity using the fictional records"}, role="manager", key="source-link-0001")
    assert result.status_code == 200, result.text
    return result.json()


def preview(api, records, key="sync-preview-0001"):
    return post(api, "/api/relationship/sync/preview", {"source": "core_lms", "records": records}, key=key)


def test_applicant_portal_to_review_to_persistent_customer_without_invented_loan(api, service):
    created = api.post("/api/relationship/onboarding-invitations", headers=headers(key="applicant-invite-0001"))
    assert created.status_code == 200
    invitation = created.json()
    page = api.get(f"/portal/{invitation['token']}")
    assert "Start your customer application" in page.text
    assert "identity_review" not in page.text
    payload = {"request_type": "APPLY", **profile()}
    for key in ("consent_calls", "consent_marketing", "dnd"):
        payload[key] = str(payload[key]).lower()
    event = portal_event(page)
    submitted = submit_form(api, invitation["token"], payload, event)
    assert submitted.status_code == 200, submitted.text
    assert "PENDING_REVIEW" in submitted.text
    assert len(service.list_customers()) == 20
    assert submit_form(api, invitation["token"], payload, event).status_code == 200
    application = api.get("/api/relationship/onboardings", headers=headers()).json()[0]
    assert application["submitted_by"] == "applicant-portal"
    oid = application["onboarding_id"]
    premature = post(api, f"/api/relationship/onboardings/{oid}/review", {"decision": "APPROVE", "note": "Need reviewed documents"}, role="manager")
    assert premature.status_code == 409
    assert premature.json()["error"] == "REVIEW_CHECKLIST_REQUIRED"
    assert post(api, f"/api/relationship/onboardings/{oid}/attest", {"identity_review": True, "document_review": True, "note": "Reviewed fictional documents"}, role="manager").status_code == 200
    approved = post(api, f"/api/relationship/onboardings/{oid}/review", {"decision": "APPROVE", "note": "Separate staff decision"}, role="manager")
    assert approved.status_code == 200
    cid = approved.json()["customer_id"]
    persisted = LocalService(service.db_path, seed=False)
    assert persisted.customer360(cid)["loans"] == []
    assert persisted.customer360(cid)["customer"]["full_name"] == profile()["full_name"]
    assert len(persisted.list_customers()) == 21
    assert "APPROVED" in api.get(f"/portal/{invitation['token']}").text
    assert api.get(f"/portal/{invitation['token']}").headers["Cache-Control"] == "no-store"


def test_reviewed_source_binding_and_mixed_sync_reach_customer360(api, service):
    cid = staff_onboard(api)
    source_link(api, cid)
    records = [source_payment(), source_interaction(), source_loan()]
    validated = preview(api, records)
    assert validated.status_code == 200
    assert validated.json()["status"] == "VALIDATED"
    run_id = validated.json()["run_id"]
    committed = api.post(f"/api/relationship/sync/runs/{run_id}/commit", headers=headers())
    assert committed.status_code == 200
    view = api.get(f"/api/relationship/customers/{cid}", headers=headers()).json()
    assert len(view["customer360"]["loans"]) == len(view["customer360"]["payments"]) == len(view["customer360"]["interactions"]) == 1
    assert view["customer360"]["metrics"]["total_outstanding"] == 280000
    assert view["customer360"]["current_decision"]["action_code"] == "RETENTION_RATE_MATCH_CALL"
    assert view["customer360"]["recommendation"]["status"] == "PENDING_APPROVAL"
    assert api.post(f"/api/relationship/sync/runs/{run_id}/commit", headers=headers()).json()["summary"]["affected_customers"] == 1
    assert api.get("/api/relationship/outbox", headers=headers("runner")).json()["counts"]["PENDING"] >= 2


def test_private_customer_invite_scoped_case_and_immediate_optout(api, service):
    action = service.recommend("C0002", service.resolve_actor("meera"))
    invitation = invite(api)
    token = invitation["token"]
    response = submit_form(api, token, {"request_type": "CASE", "category": "HARDSHIP", "subject": "Support request", "description": "Please ask an officer to discuss payment support"})
    assert response.status_code == 200
    cases = api.get("/api/relationship/customers/C0002", headers=headers()).json()["cases"]
    assert len(cases) == 1 and cases[0]["category"] == "HARDSHIP"
    assert api.get("/api/relationship/customers/C0003", headers=headers()).json()["cases"] == []
    case_id = cases[0]["case_id"]
    assert post(api, f"/api/relationship/cases/{case_id}/decision", {"status": "RESOLVED", "note": "Officer reviewed the request"}, role="manager").status_code == 200
    result = submit_form(api, token, {"request_type": "OPT_OUT"})
    assert result.status_code == 200
    assert not service.customer360("C0002")["customer"]["consent_calls"]
    assert next(a for a in service.actions() if a["action_id"] == action["action_id"])["status"] == "CANCELLED"
    assert service.customer360("C0003")["customer"]["consent_calls"]


@pytest.mark.parametrize("route", ["/api/relationship/status", "/api/relationship/onboardings", "/api/relationship/customers/C0002", "/api/relationship/sync/runs", "/api/relationship/outbox"])
def test_private_relationship_reads_require_operator_token(api, route):
    assert api.get(route).status_code == 401
    assert api.get(route, headers={"Authorization": "Bearer wrong-token"}).status_code == 401


def test_role_gates_block_review_sourcebinding_and_staff_intake(api, service):
    request = post(api, "/api/relationship/onboardings", {**profile(), "identity_review": True, "document_review": True}, key="staff-onboarding-0001")
    oid = request.json()["onboarding_id"]
    assert post(api, f"/api/relationship/onboardings/{oid}/review", {"decision": "APPROVE", "note": "forbidden"}).status_code == 403
    assert post(api, "/api/relationship/sync/customer-links", {"source": "core_lms", "source_record_id": "cust1", "customer_id": "C0002", "note": "forbidden"}, key="source-link-0001").status_code == 403
    assert post(api, "/api/relationship/onboardings", profile(), role="manager", key="manager-intake-001").status_code == 403
    assert api.post("/api/relationship/onboarding-invitations", headers=headers("manager", "manager-invite-001")).status_code == 403
    assert len(service.list_customers()) == 20


def test_staff_request_keys_bind_payload_and_create_once(api, service):
    payload = {**profile(), "identity_review": True, "document_review": True}
    first = post(api, "/api/relationship/onboardings", payload, key="staff-onboarding-0001")
    second = post(api, "/api/relationship/onboardings", payload, key="staff-onboarding-0001")
    assert second.json()["onboarding_id"] == first.json()["onboarding_id"]
    conflict = post(api, "/api/relationship/onboardings", {**payload, "full_name": "Different applicant"}, key="staff-onboarding-0001")
    assert conflict.status_code == 409 and conflict.json()["error"] == "IDEMPOTENCY_CONFLICT"
    assert len(api.get("/api/relationship/onboardings", headers=headers()).json()) == 1
    assert len(service.list_customers()) == 20


def test_invite_token_returned_once_and_customer_rotations_revoke_old_link(api):
    first = invite(api)
    replay = invite(api)
    assert replay["token"] is None
    assert replay["invite_id"] == first["invite_id"]
    second = invite(api, key="customer-invite-0002")
    assert api.get(f"/portal/{first['token']}").json()["error"] == "PORTAL_UNAVAILABLE"
    assert api.get(f"/portal/{second['token']}").status_code == 200


def test_portal_forms_cannot_supply_other_customer_or_financial_fields(api, service):
    invitation = invite(api)
    token = invitation["token"]
    for unexpected in ({"customer_id": "C0003"}, {"monthly_income": "9000000"}, {"owner": "demo-admin"}, {"priority": "URGENT"}):
        result = submit_form(api, token, {"request_type": "CASE", "subject": "Attempted escape", "description": "No mutation expected", **unexpected})
        assert result.status_code == 422
    assert api.get("/api/relationship/customers/C0002", headers=headers()).json()["cases"] == []
    assert api.get("/api/relationship/customers/C0003", headers=headers()).json()["cases"] == []
    assert service.customer360("C0002")["customer"]["monthly_income"] != 9000000


def test_customer_portal_cannot_apply_or_bypass_staff_role(api):
    invitation = invite(api)
    result = submit_form(api, invitation["token"], {"request_type": "APPLY", "full_name": "Unscoped prospect"})
    assert result.status_code == 409
    assert result.json()["error"] == "PORTAL_SCOPE_REQUIRED"
    assert api.get("/api/relationship/status", headers=headers()).json()["pending_onboardings"] == 0


def test_applicant_cannot_self_attest_kyc_through_public_form(api):
    created = api.post("/api/relationship/onboarding-invitations", headers=headers(key="applicant-invite-0001")).json()
    result = submit_form(api, created["token"], {"request_type": "APPLY", "full_name": "Fictional applicant", "identity_review": "true", "document_review": "true"})
    assert result.status_code == 422
    assert api.get("/api/relationship/status", headers=headers()).json()["pending_onboardings"] == 0


def test_portal_escapes_untrusted_name_and_case_subject_hides_private_notes(api, service):
    cid = staff_onboard(api, full_name='<script>alert("name")</script>')
    case = post(api, f"/api/relationship/customers/{cid}/cases", {"subject": '<img src=x onerror="alert(1)">', "description": "Private officer-only narrative"}, key="staff-case-0001").json()
    post(api, f"/api/relationship/cases/{case['case_id']}/decision", {"status": "IN_PROGRESS", "note": "Private staff investigation note"}, role="manager")
    page = api.get(f"/portal/{invite(api, cid)['token']}")
    assert page.status_code == 200
    assert "&lt;script&gt;" in page.text and "&lt;img" in page.text
    assert '<script>alert("name")</script>' not in page.text
    assert '<img src=x' not in page.text
    assert "Private officer-only narrative" not in page.text
    assert "Private staff investigation note" not in page.text
    assert profile()["phone"] not in page.text and profile()["email"] not in page.text
    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert page.headers["X-Frame-Options"] == "DENY"


def test_invalid_json_media_keys_and_content_limit_do_not_create_applications(api):
    path = "/api/relationship/onboardings"
    assert api.post(path, json=profile(), headers=headers()).status_code == 422
    assert api.post(path, content="{}", headers={**headers(key="bad-content-0001"), "Content-Type": "text/plain"}).status_code == 415
    assert api.post(path, content='{"monthly_income":Infinity}', headers={**headers(key="bad-json-0001"), "Content-Type": "application/json"}).status_code == 422
    assert api.post(path, content=json.dumps({"full_name": "x" * 33000}), headers={**headers(key="huge-content-0001"), "Content-Type": "application/json"}).status_code == 413
    assert post(api, path, {**profile(), "approval_status": "APPROVED"}, key="bad-fields-0001").status_code == 409
    assert api.get("/api/relationship/status", headers=headers()).json()["pending_onboardings"] == 0


def test_duplicate_or_oversized_public_form_is_rejected_without_case(api):
    token = invite(api)["token"]
    event = portal_event(api.get(f"/portal/{token}"))
    encoded = urlencode({"event_id": event, "request_type": "CASE", "subject": "First", "description": "No case should be saved"}) + "&subject=Second"
    assert api.post(f"/portal/{token}/submit", content=encoded, headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 422
    huge = {"event_id": event, "request_type": "CASE", "subject": "Oversized", "description": "x" * 8500}
    assert api.post(f"/portal/{token}/submit", data=huge).status_code == 413
    assert api.get("/api/relationship/customers/C0002", headers=headers()).json()["cases"] == []


def test_invalid_sync_previews_and_stale_commits_apply_no_partial_data(api, service):
    cid = staff_onboard(api)
    source_link(api, cid)
    invalid = preview(api, [source_loan(), source_payment() | {"loan_ref": "missing"}]).json()
    assert invalid["status"] == "INVALID"
    assert api.post(f"/api/relationship/sync/runs/{invalid['run_id']}/commit", headers=headers()).status_code == 409
    assert service.customer360(cid)["loans"] == []
    initial = preview(api, [source_loan()], key="sync-preview-0002").json()
    assert api.post(f"/api/relationship/sync/runs/{initial['run_id']}/commit", headers=headers()).status_code == 200
    stale = preview(api, [source_loan(source_version=2, outstanding=260000)], key="sync-preview-0003").json()
    fresh = preview(api, [source_loan(source_version=3, outstanding=240000)], key="sync-preview-0004").json()
    assert api.post(f"/api/relationship/sync/runs/{fresh['run_id']}/commit", headers=headers()).status_code == 200
    assert api.post(f"/api/relationship/sync/runs/{stale['run_id']}/commit", headers=headers()).json()["error"] == "SYNC_CHANGED_SINCE_PREVIEW"
    assert service.customer360(cid)["loans"][0]["outstanding"] == 240000


def test_missing_and_invalid_portal_links_never_disclose_customer_existence(api):
    invalid = api.get("/portal/not-a-valid-capability")
    guessed = api.get("/portal/" + "a" * 43)
    assert invalid.status_code == guessed.status_code == 404
    assert invalid.json() == guessed.json()
    assert invalid.json()["error"] == "PORTAL_UNAVAILABLE"


def test_portal_hardship_recomputes_growth_and_revokes_old_offer(api, service):
    analyst = service.resolve_actor("meera")
    credit = service.resolve_actor("kavya")
    action = service.recommend("C0003", analyst)
    assert action["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    service.approve_action(action["action_id"], credit, note="Fictional credit review")
    with service._db(write=True) as con:
        offer_token = service._create_offer(con, service._action(con, action["action_id"]))
    token = invite(api, "C0003")["token"]
    response = submit_form(api, token, {"request_type": "CASE", "category": "HARDSHIP", "subject": "My job was lost", "description": "I lost my job and cannot afford my current repayments. Please ask an officer for support."})
    assert response.status_code == 200
    view = service.customer360("C0003")
    assert view["metrics"]["hardship_flag"] is True
    assert view["metrics"]["topup_eligible"] is False
    assert view["current_decision"]["action_code"] != "TOPUP_PREAPPROVAL_CALL"
    assert next(a for a in service.actions() if a["action_id"] == action["action_id"])["status"] == "CANCELLED"
    assert api.get(f"/offer/{offer_token}").status_code == 410
    blocked = post(api, f"/api/actions/{action['action_id']}/execute", {"mode": "simulate", "outcome": "ACCEPT"}, role="runner")
    assert blocked.status_code == 409 and blocked.json()["error"] == "APPROVAL_REQUIRED"


def test_malformed_review_decision_and_case_state_return_domain_error_not_500(api):
    request = post(api, "/api/relationship/onboardings", {**profile(), "identity_review": True, "document_review": True}, key="staff-onboarding-0001").json()
    malformed_review = post(api, f"/api/relationship/onboardings/{request['onboarding_id']}/review", {"decision": [], "note": "Malformed input"}, role="manager")
    assert malformed_review.status_code == 409
    assert malformed_review.json()["error"] == "INVALID_DECISION"
    case = post(api, "/api/relationship/customers/C0002/cases", {"subject": "Help", "description": "A service request"}, key="staff-case-0001").json()
    malformed_state = post(api, f"/api/relationship/cases/{case['case_id']}/decision", {"status": {}, "note": "Malformed input"}, role="manager")
    assert malformed_state.status_code == 409
    assert malformed_state.json()["error"] == "INVALID_CASE_STATUS"
