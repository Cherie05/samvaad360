"""Operational CRM acceptance checks; no remote databases, emails, or carrier calls."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

import samvaad.relationship as crm
from samvaad.models import ActionError, Actor
from samvaad.relationship import RelationshipService, normalize_customer, normalize_sync_record
from samvaad.service import timestamp, utcnow


@pytest.fixture
def relationship(service):
    return RelationshipService(service)


def customer(**changes):
    return {"full_name": "New Fictional Borrower", "city": "Chennai", "segment": "SALARIED",
            "monthly_income": 90000, "preferred_language": "English", "phone": "+15005550009",
            "email": "fictional-onboarding@example.invalid", "consent_calls": True,
            "consent_marketing": True, "dnd": False, "consent_reference": "Recorded fictional pilot intake",
            "identity_review": True, "document_review": True, **changes}


def import_customer(source_id="cust1", version=1, **changes):
    fields = {k: v for k, v in customer().items() if k in crm.CUSTOMER_FIELDS}
    return {"record_type": "customer", "source_record_id": source_id, "source_version": version, **fields, **changes}


def loan(**changes):
    return {"record_type": "loan", "source_record_id": "loan1", "source_version": 1,
            "customer_ref": "cust1", "product": "PERSONAL_LOAN", "principal": 500000,
            "outstanding": 300000, "interest_rate": 14, "emi": 11000,
            "relationship_months": 36, "current_dpd": 0, "status": "ACTIVE",
            "disbursed_on": "2023-01-01", **changes}


def payment(**changes):
    return {"record_type": "payment", "source_record_id": "payment1", "source_version": 1,
            "loan_ref": "loan1", "due_date": utcnow().date().isoformat(), "paid_date": utcnow().date().isoformat(),
            "amount_due": 11000, "amount_paid": 11000, "status": "PAID", **changes}


def interaction(**changes):
    return {"record_type": "interaction", "source_record_id": "call1", "source_version": 1,
            "customer_ref": "cust1", "channel": "CALL_IN", "text": "I am unhappy about your high interest rate. I want foreclosure and balance transfer. Another bank offered 11 percent.",
            "ts": timestamp(), **changes}


def onboard(relationship, analyst, manager):
    application = relationship.submit_onboarding(customer(), analyst, "onboard-0001")
    return relationship.review_onboarding(application["onboarding_id"], "APPROVE", "Reviewed fictional documents", manager)["customer_id"]


def commit(relationship, records, analyst, key="sync-run-0001"):
    preview = relationship.preview_sync("lms", records, analyst, key)
    assert preview["errors"] == []
    return relationship.commit_sync(preview["run_id"], analyst)


def expect(code, fn):
    with pytest.raises(ActionError) as error:
        fn()
    assert error.value.code == code


def test_onboarding_persists_private_customer_once_without_inventing_loan(relationship, service, analyst, manager):
    application = relationship.submit_onboarding(customer(), analyst, "onboard-0001")
    assert application["status"] == "PENDING_REVIEW"
    assert len(service.list_customers()) == 20
    assert relationship.submit_onboarding(customer(), analyst, "onboard-0001")["onboarding_id"] == application["onboarding_id"]
    approved = relationship.review_onboarding(application["onboarding_id"], "APPROVE", "Fictional document review", manager)
    replay = relationship.review_onboarding(application["onboarding_id"], "APPROVE", "Fictional document review", manager)
    assert replay["customer_id"] == approved["customer_id"]
    persisted = RelationshipService(service).customer_relationship(approved["customer_id"], analyst)
    assert approved["customer_id"].startswith("CRM")
    assert persisted["customer360"]["loans"] == []
    assert persisted["relationship"]["lifecycle_stage"] == "PROSPECT"
    assert len(service.list_customers()) == 21
    assert relationship.status(analyst)["pending_exports"] == 1


def test_changed_onboarding_key_is_rejected(relationship, analyst):
    relationship.submit_onboarding(customer(), analyst, "onboard-0001")
    expect("IDEMPOTENCY_CONFLICT", lambda: relationship.submit_onboarding(customer(full_name="Different"), analyst, "onboard-0001"))


@pytest.mark.parametrize("bad", [Actor("meera", "ADMIN"), None, Actor("unknown", "ANALYST")])
def test_forged_staff_identity_cannot_create_customer(relationship, bad):
    expect("FORBIDDEN", lambda: relationship.submit_onboarding(customer(), bad, "onboard-0001"))


def test_review_requires_actual_staff_role_and_attested_checklist(relationship, analyst, manager):
    application = relationship.submit_onboarding(customer(identity_review=False), analyst, "onboard-0001")
    expect("FORBIDDEN", lambda: relationship.review_onboarding(application["onboarding_id"], "APPROVE", "reviewed", analyst))
    expect("REVIEW_CHECKLIST_REQUIRED", lambda: relationship.review_onboarding(application["onboarding_id"], "APPROVE", "reviewed", manager))
    relationship.attest_onboarding(application["onboarding_id"], True, True, "Staff reviewed documents", manager)
    assert relationship.review_onboarding(application["onboarding_id"], "APPROVE", "reviewed", manager)["customer_id"]


def test_onboarding_rejection_is_final_and_creates_no_customer(relationship, service, analyst, manager):
    application = relationship.submit_onboarding(customer(), analyst, "onboard-0001")
    rejected = relationship.review_onboarding(application["onboarding_id"], "REJECT", "Insufficient document review", manager)
    assert rejected["customer_id"] is None
    assert len(service.list_customers()) == 20
    expect("INVALID_STATE", lambda: relationship.review_onboarding(application["onboarding_id"], "APPROVE", "reviewed", manager))


def test_contact_permission_requires_bounded_reference(relationship, analyst):
    expect("CONSENT_REFERENCE_REQUIRED", lambda: relationship.submit_onboarding(customer(consent_reference=""), analyst, "onboard-0001"))


def test_duplicate_contact_cannot_create_second_approved_customer(relationship, analyst, manager):
    onboard(relationship, analyst, manager)
    application = relationship.submit_onboarding(customer(full_name="Another person"), analyst, "onboard-0002")
    expect("DUPLICATE_CONTACT", lambda: relationship.review_onboarding(application["onboarding_id"], "APPROVE", "reviewed", manager))


@pytest.mark.parametrize("change", [{"monthly_income": float("nan")}, {"monthly_income": float("inf")},
    {"monthly_income": True}, {"consent_calls": "true"}, {"phone": "1234"}, {"email": "bad"},
    {"full_name": "\x00hidden"}, {"preferred_language": "Unsupported"}, {"approved": True}])
def test_customer_validation_rejects_unsafe_or_unsupported_fields(change):
    with pytest.raises(ActionError):
        normalize_customer(customer(**change))


def test_concurrent_onboarding_requests_create_single_application(relationship, analyst):
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: relationship.submit_onboarding(customer(), analyst, "onboard-atomic"), range(6)))
    assert len({r["onboarding_id"] for r in results}) == 1
    assert relationship.status(analyst)["pending_onboardings"] == 1


def test_versioned_mixed_import_resolves_unsorted_references_atomically(relationship, analyst):
    result = commit(relationship, [payment(), interaction(), loan(), import_customer()], analyst)
    assert result["summary"]["affected_customers"] == 1
    cid = relationship._local_id("lms", "customer", "cust1")
    view = relationship.customer_relationship(cid, analyst)
    assert len(view["customer360"]["loans"]) == len(view["customer360"]["payments"]) == len(view["customer360"]["interactions"]) == 1
    assert view["customer360"]["customer"]["consent_calls"] is False
    assert view["relationship"]["lifecycle_stage"] == "ACTIVE_RELATIONSHIP"
    assert view["customer360"]["interactions"][0]["simulated"] == 0
    assert relationship.commit_sync(result["run_id"], analyst)["status"] == "COMMITTED"


def test_same_source_version_content_is_noop_but_changed_content_conflicts(relationship, analyst):
    row = import_customer()
    commit(relationship, [row], analyst)
    assert commit(relationship, [row], analyst, "sync-run-0002")["summary"]["affected_customers"] == 0
    changed = relationship.preview_sync("lms", [import_customer(city="Mumbai")], analyst, "sync-run-0003")
    assert changed["status"] == "INVALID"
    assert changed["errors"][0]["code"] == "SOURCE_VERSION_CONFLICT"
    expect("SYNC_VALIDATION_REQUIRED", lambda: relationship.commit_sync(changed["run_id"], analyst))
    assert relationship.outbox_status(analyst)["counts"] == {"PENDING": 1}


def test_stale_versions_are_rejected_and_preview_is_revalidated_on_commit(relationship, analyst):
    commit(relationship, [import_customer()], analyst)
    v2 = relationship.preview_sync("lms", [import_customer(version=2, city="Delhi")], analyst, "sync-run-0002")
    commit(relationship, [import_customer(version=3, city="Mumbai")], analyst, "sync-run-0003")
    expect("SYNC_CHANGED_SINCE_PREVIEW", lambda: relationship.commit_sync(v2["run_id"], analyst))
    older = relationship.preview_sync("lms", [import_customer(version=2)], analyst, "sync-run-0004")
    assert older["errors"][0]["code"] == "STALE_SOURCE_VERSION"


def test_invalid_batch_applies_nothing_and_reports_missing_references(relationship, service, analyst):
    preview = relationship.preview_sync("lms", [import_customer(), loan(customer_ref="missing")], analyst, "sync-run-0001")
    assert preview["status"] == "INVALID"
    assert any(e["code"] == "MISSING_REFERENCE" for e in preview["errors"])
    expect("SYNC_VALIDATION_REQUIRED", lambda: relationship.commit_sync(preview["run_id"], analyst))
    assert len(service.list_customers()) == 20
    assert relationship.outbox_status(analyst)["events"] == []


def test_commit_failure_rolls_back_entire_batch(relationship, service, analyst, monkeypatch):
    preview = relationship.preview_sync("lms", [import_customer(), loan(), payment()], analyst, "sync-run-0001")
    original = relationship._apply_record
    def fail_on_payment(con, source, row, existing, actor):
        if row["record_type"] == "payment":
            raise RuntimeError("injected storage failure")
        return original(con, source, row, existing, actor)
    monkeypatch.setattr(relationship, "_apply_record", fail_on_payment)
    with pytest.raises(RuntimeError):
        relationship.commit_sync(preview["run_id"], analyst)
    assert len(service.list_customers()) == 20
    with service._db() as con:
        assert con.execute("SELECT COUNT(*) FROM relationship_sources").fetchone()[0] == 0
    assert relationship.sync_run(preview["run_id"], analyst)["status"] == "VALIDATED"


@pytest.mark.parametrize("records", [[import_customer(), import_customer()], [loan()],
    [import_customer(source_version=0)], [loan(outstanding=-1)], [loan(emi=float("nan"))],
    [payment(status="APPROVED")], [interaction(channel="ACTION_OUTCOME")],
    [interaction(ts="2026-10-06T12:00:00")], [import_customer(approved_by="owner")]])
def test_sync_preview_rejects_duplicates_unsupported_decisions_and_invalid_values(relationship, analyst, records):
    try:
        preview = relationship.preview_sync("lms", records, analyst, "sync-invalid-001")
        assert preview["status"] == "INVALID"
        assert preview["errors"]
    except ActionError as error:
        assert error.code == "INVALID_BATCH"


def test_onboarded_customer_can_be_reviewed_linked_to_source_and_get_loan(relationship, analyst, manager):
    cid = onboard(relationship, analyst, manager)
    link = relationship.link_source_customer("lms", "cust1", cid, manager, "link-source-0001", "Checked exact source identity")
    assert link["source_version"] == 0
    result = commit(relationship, [loan(), payment(), interaction()], analyst)
    view = relationship.customer_relationship(cid, analyst)
    assert result["summary"]["affected_customers"] == 1
    assert view["customer360"]["loans"][0]["customer_id"] == cid
    assert view["customer360"]["current_decision"]["action_code"] == "RETENTION_RATE_MATCH_CALL"
    assert view["customer360"]["recommendation"]["status"] == "PENDING_APPROVAL"


def test_source_mapping_is_privileged_immutable_and_blocks_conflicting_contact(relationship, analyst, manager):
    cid = onboard(relationship, analyst, manager)
    expect("FORBIDDEN", lambda: relationship.link_source_customer("lms", "cust1", cid, analyst, "link-source-0001", "reviewed"))
    relationship.link_source_customer("lms", "cust1", cid, manager, "link-source-0001", "reviewed")
    expect("SOURCE_OWNERSHIP_CONFLICT", lambda: relationship.link_source_customer("lms", "cust1", "C0002", manager, "link-source-0002", "reviewed"))
    invalid = relationship.preview_sync("lms", [import_customer(phone="+15005550010")], analyst, "sync-invalid-001")
    assert any(e["code"] == "SOURCE_CONTACT_BINDING_CONFLICT" for e in invalid["errors"])


def test_changed_evidence_invalidates_old_financial_approval_and_creates_fresh_one(relationship, service, analyst, manager):
    relationship.link_source_customer("lms", "cust1", "C0002", manager, "link-source-0001", "Exact reviewed fixture mapping")
    old = service.recommend("C0002", analyst)
    service.approve_action(old["action_id"], manager, note="Synthetic staff review")
    commit(relationship, [interaction()], analyst)
    rows = service.actions()
    old_row = next(a for a in rows if a["action_id"] == old["action_id"])
    assert old_row["status"] == "CANCELLED"
    fresh = next(a for a in rows if a["customer_id"] == "C0002" and a["status"] == "PENDING_APPROVAL")
    assert fresh["action_id"] != old["action_id"]
    assert fresh["approved_by"] is None


def test_opt_out_is_not_reenabled_by_new_source_version(relationship, service, analyst, manager):
    cid = onboard(relationship, analyst, manager)
    relationship.link_source_customer("lms", "cust1", cid, manager, "link-source-0001", "reviewed")
    commit(relationship, [import_customer()], analyst)
    invite = relationship.issue_portal_invite(cid, analyst, "portal-invite-01")
    relationship.portal_submit(invite["token"], {"request_type": "OPT_OUT"}, "portal-optout-01")
    commit(relationship, [import_customer(version=2)], analyst, "sync-run-0002")
    saved = service.customer360(cid)["customer"]
    assert not saved["consent_calls"] and not saved["consent_marketing"]


def test_case_assignment_followup_resolution_and_scoped_views(relationship, analyst, manager):
    due = timestamp(utcnow() + timedelta(days=1))
    case = relationship.add_case("C0002", {"category": "COMPLAINT", "priority": "HIGH", "subject": "Review rate communication",
        "description": "Fictional support request", "due_at": due, "owner": manager.user_id}, analyst, "case-create-001")
    assert relationship.customer_relationship("C0002", analyst)["relationship"]["next_followup_at"] == due
    expect("INVALID_STATE", lambda: relationship.update_case(case["case_id"], "CLOSED", "Closed directly", manager))
    relationship.update_case(case["case_id"], "RESOLVED", "Officer responded", manager)
    relationship.update_case(case["case_id"], "CLOSED", "Customer confirmed closure", manager)
    assert relationship.customer_relationship("C0002", analyst)["relationship"]["next_followup_at"] is None
    expect("INVALID_STATE", lambda: relationship.update_case(case["case_id"], "OPEN", "reopened", manager))


def test_portal_tokens_are_hash_only_bound_to_customer_and_retries_never_redisclose(relationship, service, analyst):
    created = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    replay = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    assert replay["token"] is None
    assert replay["invite_id"] == created["invite_id"]
    with service._db() as con:
        dump = "\n".join(con.iterdump())
    assert created["token"] not in dump
    view = relationship.portal_view(created["token"])
    assert view["customer_id"] == "C0002"
    assert "monthly_income" not in json.dumps(view)
    assert service.customer360("C0002")["customer"]["phone"] not in json.dumps(view)
    assert "phone_masked" in view["contact"]
    assert "loans" not in view


def test_portal_request_cannot_escape_customer_scope_or_change_financial_facts(relationship, analyst):
    first = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    second = relationship.issue_portal_invite("C0003", analyst, "portal-invite-02")
    request = {"request_type": "CASE", "subject": "Callback", "description": "Please contact my officer"}
    one = relationship.portal_submit(first["token"], request, "portal-case-0001")
    two = relationship.portal_submit(second["token"], request, "portal-case-0001")
    assert one["case"]["case_id"] != two["case"]["case_id"]
    assert relationship.portal_submit(first["token"], request, "portal-case-0001")["replayed"]
    expect("IDEMPOTENCY_CONFLICT", lambda: relationship.portal_submit(first["token"], {**request, "subject": "Changed"}, "portal-case-0001"))
    expect("INVALID_PAYLOAD", lambda: relationship.portal_submit(first["token"], {"request_type": "CASE", "customer_id": "C0003"}, "portal-escape-01"))
    expect("INVALID_PAYLOAD", lambda: relationship.portal_submit(first["token"], {"request_type": "CONTACT_PREFERENCES", "monthly_income": 999999}, "portal-escape-02"))


def test_portal_optout_revokes_actions_offers_and_phone_recipients(relationship, service, analyst, manager):
    from samvaad.telephony import TelephonyService, TelephonySettings
    TelephonyService(service, TelephonySettings())
    old = service.recommend("C0002", analyst)
    service.approve_action(old["action_id"], manager, note="Fictional review")
    with service._db(write=True) as con:
        service._create_offer(con, service._action(con, old["action_id"]))
        con.execute("INSERT INTO telephony_recipients VALUES ('recipient-1','C0002','+15005550009','alternate','permission','arjun','VERIFIED',NULL,?,NULL,?,0)", (timestamp(), timestamp(utcnow() + timedelta(days=1))))
    invite = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    result = relationship.portal_submit(invite["token"], {"request_type": "OPT_OUT"}, "portal-optout-01")
    assert result["contact"]["consent_calls"] is False
    assert next(a for a in service.actions() if a["action_id"] == old["action_id"])["status"] == "CANCELLED"
    assert service.offers("C0002")[0]["status"] == "REVOKED"
    with service._db() as con:
        assert con.execute("SELECT status FROM telephony_recipients").fetchone()[0] == "REVOKED"
    expect("CONSENT_REACTIVATION_BLOCKED", lambda: relationship.portal_submit(invite["token"], {"request_type": "CONTACT_PREFERENCES", "consent_calls": True}, "portal-consent-01"))


def test_expired_revoked_and_invalid_portal_links_fail_identically(relationship, analyst, monkeypatch):
    first = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    second = relationship.issue_portal_invite("C0002", analyst, "portal-invite-02")
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_view(first["token"]))
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_view("invalid"))
    future = utcnow() + timedelta(days=2)
    monkeypatch.setattr(crm, "utcnow", lambda: future)
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_view(second["token"]))
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_submit(second["token"], {"request_type": "OPT_OUT"}, "portal-optout-01"))


def test_applicant_invite_creates_only_one_pending_review_then_tracks_approval(relationship, service, analyst, manager):
    invite = relationship.issue_onboarding_invite(analyst, "prospect-invite-01")
    assert relationship.portal_view(invite["token"])["application_status"] == "NOT_SUBMITTED"
    payload = {"request_type": "APPLY", **{k: v for k, v in customer().items() if k in crm.CUSTOMER_FIELDS | {"consent_reference"}}}
    result = relationship.portal_submit(invite["token"], payload, "prospect-apply-01")
    assert result["status"] == "PENDING_REVIEW"
    assert len(service.list_customers()) == 20
    assert relationship.portal_submit(invite["token"], payload, "prospect-apply-01")["replayed"]
    expect("APPLICATION_ALREADY_SUBMITTED", lambda: relationship.portal_submit(invite["token"], payload, "prospect-apply-02"))
    expect("REVIEW_CHECKLIST_REQUIRED", lambda: relationship.review_onboarding(result["onboarding_id"], "APPROVE", "reviewed", manager))
    relationship.attest_onboarding(result["onboarding_id"], True, True, "Staff fictional document review", manager)
    approved = relationship.review_onboarding(result["onboarding_id"], "APPROVE", "reviewed", manager)
    view = relationship.portal_view(invite["token"])
    assert view["application_status"] == "APPROVED"
    assert view["customer_id"] == approved["customer_id"]
    assert "payload" not in view
    expect("PORTAL_SCOPE_REQUIRED", lambda: relationship.portal_submit(invite["token"], {"request_type": "OPT_OUT"}, "portal-optout-01"))


def test_applicant_cannot_self_certify_staff_review_or_use_customer_invite(relationship, analyst):
    invite = relationship.issue_onboarding_invite(analyst, "prospect-invite-01")
    expect("INVALID_PAYLOAD", lambda: relationship.portal_submit(invite["token"], {"request_type": "APPLY", **customer()}, "prospect-apply-01"))
    existing = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    payload = {"request_type": "APPLY", "full_name": "Fictional prospect"}
    expect("PORTAL_SCOPE_REQUIRED", lambda: relationship.portal_submit(existing["token"], payload, "prospect-apply-01"))


def test_private_export_payload_hashes_contacts_with_monotonic_customer_versions(relationship, analyst, admin):
    relationship.add_case("C0002", {"subject": "Help", "description": "Private description"}, analyst, "case-create-001")
    relationship.add_case("C0002", {"subject": "Help again", "description": "Second private description"}, analyst, "case-create-002")
    first = relationship.claim_outbox(admin, limit=5, lease_seconds=600)
    assert len(first) == 1  # One customer can never have parallel version leases.
    event = first[0]
    encoded = json.dumps(event["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert event["event_hash"] == hashlib.sha256(encoded.encode()).hexdigest()
    assert event["payload"]["customer"]["customer_id"] == event["customer_id"]
    assert "phone" in event["payload"]["customer"]
    assert relationship.claim_outbox(admin) == []
    relationship.complete_outbox(event["event_id"], event["lease_token"], admin)
    second = relationship.claim_outbox(admin)
    assert second[0]["version"] == event["version"] + 1


def test_outbox_expired_ack_is_rejected_and_retry_stays_same_version(relationship, analyst, admin, monkeypatch):
    relationship.add_case("C0002", {"subject": "Help", "description": "Private request"}, analyst, "case-create-001")
    event = relationship.claim_outbox(admin, lease_seconds=30)[0]
    expect("OUTBOX_LEASE_EXPIRED", lambda: relationship.complete_outbox(event["event_id"], "a" * 32, admin))
    now = utcnow() + timedelta(seconds=31)
    monkeypatch.setattr(crm, "utcnow", lambda: now)
    # timestamp delegates service.utcnow; pass expiry comparison through explicit utcnow.
    monkeypatch.setattr(crm, "timestamp", lambda value=None: (value or now).isoformat())
    expect("OUTBOX_LEASE_EXPIRED", lambda: relationship.complete_outbox(event["event_id"], event["lease_token"], admin))
    reclaimed = relationship.claim_outbox(admin)[0]
    assert reclaimed["event_id"] == event["event_id"]
    assert reclaimed["lease_token"] != event["lease_token"]
    relationship.complete_outbox(reclaimed["event_id"], reclaimed["lease_token"], admin, error="password=secret,private SQL body")
    retried = relationship.claim_outbox(admin)[0]
    assert retried["version"] == event["version"]
    assert relationship.outbox_status(admin)["events"][0]["last_error"] == "EXPORT_FAILED"


def test_audit_excludes_private_contacts_text_and_portal_capabilities(relationship, service, analyst, manager):
    cid = onboard(relationship, analyst, manager)
    invite = relationship.issue_portal_invite(cid, analyst, "portal-invite-01")
    relationship.portal_submit(invite["token"], {"request_type": "CASE", "subject": "Private subject", "description": "Secret borrower narrative"}, "portal-case-0001")
    audit = json.dumps(service.audit())
    for sensitive in [customer()["phone"], customer()["email"], "Secret borrower narrative", invite["token"], "Private subject"]:
        assert sensitive not in audit


def test_concurrent_sync_commit_creates_single_source_record_and_export(relationship, analyst):
    preview = relationship.preview_sync("lms", [import_customer()], analyst, "sync-run-0001")
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: relationship.commit_sync(preview["run_id"], analyst), range(5)))
    assert all(result["status"] == "COMMITTED" for result in results)
    assert relationship.status(analyst)["customers"] == 21
    assert relationship.outbox_status(analyst)["counts"] == {"PENDING": 1}


def test_imported_contact_change_cannot_reuse_old_contact_permission(relationship, service, analyst, manager):
    cid = onboard(relationship, analyst, manager)
    relationship.link_source_customer("lms", "cust1", cid, manager, "link-source-0001", "Reviewed exact customer")
    commit(relationship, [import_customer()], analyst)
    assert service.customer360(cid)["customer"]["consent_calls"]
    commit(relationship, [import_customer(version=2, phone="+15005550010")], analyst, "sync-run-0002")
    current = service.customer360(cid)["customer"]
    assert current["phone"] == "+15005550010"
    assert current["consent_calls"] is False and current["consent_marketing"] is False


@pytest.mark.parametrize("kind", [[], {}, 42, None])
def test_malformed_record_types_are_reported_as_invalid_rows(relationship, analyst, kind):
    result = relationship.preview_sync("lms", [{"record_type": kind}], analyst, "sync-invalid-001")
    assert result["errors"][0]["code"] == "INVALID_RECORD_TYPE"


def test_preview_error_row_numbers_preserve_original_upload_positions(relationship, analyst):
    result = relationship.preview_sync("lms", [{"record_type": "unsupported"}, import_customer(), loan(customer_ref="missing")], analyst, "sync-invalid-001")
    assert [(error["row"], error["code"]) for error in result["errors"]] == [(1, "INVALID_RECORD_TYPE"), (3, "MISSING_REFERENCE")]


def test_payment_cannot_move_between_loans_of_the_same_customer(relationship, analyst):
    commit(relationship, [import_customer(), loan(), loan(source_record_id="loan2"), payment()], analyst)
    result = relationship.preview_sync("lms", [payment(source_version=2, loan_ref="loan2")], analyst, "sync-invalid-001")
    assert result["status"] == "INVALID"
    assert result["errors"][0]["code"] == "SOURCE_OWNERSHIP_CONFLICT"


def test_invalid_portal_request_shapes_fail_closed(relationship, analyst):
    invite = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")
    expect("INVALID_PORTAL_REQUEST", lambda: relationship.portal_submit(invite["token"], {"request_type": []}, "portal-invalid-01"))
    expect("INVALID_PORTAL_REQUEST", lambda: relationship.portal_submit(invite["token"], {"request_type": "CONTACT_PREFERENCES", "subject": "ignored"}, "portal-invalid-02"))
    expect("INVALID_FIELD", lambda: relationship.portal_submit(invite["token"], {"request_type": "CONTACT_PREFERENCES", "preferred_language": []}, "portal-invalid-03"))


def test_hardship_case_recomputes_growth_and_retires_financial_approval_atomically(relationship, service, analyst, credit):
    old = service.recommend("C0003", analyst)
    service.approve_action(old["action_id"], credit, note="Fictional credit review")
    with service._db(write=True) as con:
        offer = service._create_offer(con, service._action(con, old["action_id"]))
    token = relationship.issue_portal_invite("C0003", analyst, "portal-invite-01")["token"]
    relationship.portal_submit(token, {"request_type": "CASE", "category": "HARDSHIP", "subject": "Job loss",
        "description": "I lost my job and cannot afford these repayments."}, "portal-hardship-01")
    view = service.customer360("C0003")
    assert view["metrics"]["hardship_flag"] is True
    assert view["metrics"]["topup_eligible"] is False
    evidence = next(i for i in view["interactions"] if i["interaction_id"].startswith("CRM-CASE-"))
    assert evidence["simulated"] == 0
    assert evidence["intent"] == "financial hardship"
    assert evidence["text"] == "Job loss\nI lost my job and cannot afford these repayments."
    assert next(a for a in service.actions() if a["action_id"] == old["action_id"])["status"] == "CANCELLED"
    expect("OFFER_REVOKED", lambda: service.get_offer(offer))


def test_case_approval_requires_human_review_for_nonfinancial_callback(relationship, service, analyst, manager):
    relationship.add_case("C0001", {"category": "HARDSHIP", "subject": "Repayment help", "description": "Please arrange support for my repayment situation"}, analyst, "case-hardship-01")
    action = next(a for a in service.actions() if a["customer_id"] == "C0001" and a["status"] == "PENDING_APPROVAL")
    assert action["action_code"] == "HARDSHIP_RESTRUCTURE_CALL"
    assert action["approval_role"] == "MANAGER"
    assert action["approved_by"] is None
    assert service.approve_action(action["action_id"], manager, note="Reviewed support request")["status"] == "APPROVED"


def test_staff_checklist_and_identity_binding_notes_persist_privately(relationship, service, analyst, manager):
    app = relationship.submit_onboarding(customer(identity_review=False, document_review=False), analyst, "onboard-note-001")
    relationship.attest_onboarding(app["onboarding_id"], True, True, " Private checklist evidence ", manager)
    relationship.link_source_customer("lms", "cust1", "C0002", manager, "link-note-0001", "Private reviewed identity evidence")
    with service._db() as con:
        notes = [dict(r) for r in con.execute("SELECT * FROM relationship_review_evidence ORDER BY created_at")]
    assert [n["note"] for n in notes] == ["Private checklist evidence", "Private reviewed identity evidence"]
    assert all(n["actor"] == manager.user_id for n in notes)
    assert "Private checklist evidence" not in json.dumps(service.audit())
    assert "Private reviewed identity evidence" not in json.dumps(service.audit())


def test_portal_case_quota_never_blocks_optout_or_reduced_preferences(relationship, analyst):
    token = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")["token"]
    for index in range(20):
        relationship.portal_submit(token, {"request_type": "CASE", "subject": "Service request", "description": "Fictional request"}, f"portal-case-{index:04d}")
    expect("PORTAL_REQUEST_LIMIT", lambda: relationship.portal_submit(token, {"request_type": "CASE", "subject": "One more", "description": "Blocked by case limit"}, "portal-case-0020"))
    result = relationship.portal_submit(token, {"request_type": "OPT_OUT"}, "portal-optout-01")
    assert result["contact"]["consent_calls"] is False
    events = relationship.outbox_status(analyst)["counts"]["PENDING"]
    relationship.portal_submit(token, {"request_type": "OPT_OUT"}, "portal-optout-02")
    relationship.portal_submit(token, {"request_type": "CONTACT_PREFERENCES", "consent_calls": False, "consent_marketing": False}, "portal-reduce-01")
    assert relationship.outbox_status(analyst)["counts"]["PENDING"] == events


def test_sync_cannot_bypass_unresolved_case_human_review_gate(relationship, service, analyst, manager):
    relationship.add_case("C0001", {"category": "HARDSHIP", "subject": "Support", "description": "I need help with repayments"}, analyst, "case-hardship-01")
    relationship.link_source_customer("lms", "cust1", "C0001", manager, "link-source-0001", "Reviewed fixture source mapping")
    commit(relationship, [interaction(text="Please review my outstanding repayment")], analyst)
    actions = [a for a in service.actions() if a["customer_id"] == "C0001" and a["status"] != "CANCELLED"]
    assert actions and all(a["status"] == "PENDING_APPROVAL" and a["approval_role"] == "MANAGER" for a in actions)


def test_case_human_approval_executes_service_callback_without_financial_invitation(relationship, service, analyst, manager, runner):
    relationship.add_case("C0001", {"category": "HARDSHIP", "subject": "Repayment support", "description": "Please help with my current repayment situation"}, analyst, "case-hardship-01")
    action = next(a for a in service.actions() if a["customer_id"] == "C0001" and a["status"] == "PENDING_APPROVAL")
    service.approve_action(action["action_id"], manager, note="Officer reviewed this support request")
    completed = service.execute_action(action["action_id"], runner, mode="simulate", outcome="ACCEPT")
    assert completed["status"] == "COMPLETED"
    assert completed["execution_mode"] == "simulate"
    assert service.offers("C0001") == []
    assert any(row["event"] == "RESTRUCTURE_REVIEW_REQUESTED" for row in service.audit("C0001"))


def test_fresh_unchanged_withdrawal_keys_cannot_grow_request_table(relationship, service, analyst):
    token = relationship.issue_portal_invite("C0002", analyst, "portal-invite-01")["token"]
    original = relationship.portal_submit(token, {"request_type": "OPT_OUT"}, "portal-optout-01")
    with service._db() as con:
        before = con.execute("SELECT COUNT(*) FROM relationship_requests").fetchone()[0]
    for index in range(30):
        result = relationship.portal_submit(token, {"request_type": "OPT_OUT"}, f"portal-noop-{index:04d}")
        assert result["unchanged"] is True
    with service._db() as con:
        after = con.execute("SELECT COUNT(*) FROM relationship_requests").fetchone()[0]
    assert before == after
    replay = relationship.portal_submit(token, {"request_type": "OPT_OUT"}, "portal-optout-01")
    assert replay["replayed"] is True and replay["contact"] == original["contact"]


def test_reset_clears_relationship_records_in_foreign_key_safe_order(relationship, service, analyst, manager, admin):
    application = relationship.submit_onboarding(customer(identity_review=False), analyst, "onboard-reset-001")
    relationship.attest_onboarding(application["onboarding_id"], True, True, "Private review evidence", manager)
    approved = relationship.review_onboarding(application["onboarding_id"], "APPROVE", "Fictional document review", manager)
    cid = approved["customer_id"]
    relationship.link_source_customer("lms", "cust1", cid, manager, "link-reset-0001", "Private reviewed mapping")
    commit(relationship, [loan(), payment()], analyst)
    relationship.add_case(cid, {"subject": "Service", "description": "Private request"}, analyst, "case-reset-0001")
    customer_invite = relationship.issue_portal_invite(cid, analyst, "portal-reset-0001")
    applicant_invite = relationship.issue_onboarding_invite(analyst, "applicant-reset-001")
    assert relationship.outbox_status(analyst)["events"]
    assert service.reset_demo(admin)["status"] == "SEEDED"
    with service._db() as con:
        tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'relationship_%'")]
        assert tables
        for table in tables:
            assert con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] == 0
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert len(service.list_customers()) == 20
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_view(customer_invite["token"]))
    expect("PORTAL_UNAVAILABLE", lambda: relationship.portal_view(applicant_invite["token"]))


@pytest.mark.parametrize("call_state", ["DISPATCH_UNCERTAIN", "queued", "in-progress"])
def test_reset_refuses_unresolved_carrier_calls_and_preserves_crm_records(relationship, service, analyst, admin, call_state):
    from samvaad.telephony import TelephonyService, TelephonySettings
    TelephonyService(service, TelephonySettings())
    relationship.add_case("C0002", {"subject": "Keep record", "description": "Do not delete while delivery is uncertain"}, analyst, "case-keep-0001")
    action = service.recommend("C0002", analyst)
    with service._db(write=True) as con:
        con.execute("INSERT INTO telephony_recipients VALUES ('reset-recipient','C0002','+15005550009','alternate','permission','arjun','VERIFIED',NULL,?,NULL,?,0)", (timestamp(), timestamp(utcnow() + timedelta(days=1))))
        con.execute("""INSERT INTO telephony_calls(call_id,action_id,recipient_id,customer_id,idempotency_key,requested_by,status,conversation_state,created_at)
                       VALUES ('reset-call',?,'reset-recipient','C0002','reset-call-unique','arjun',?,'AWAIT_PERMISSION',?)""", (action["action_id"], call_state, timestamp()))
    expect("ACTIVE_CALLS", lambda: service.reset_demo(admin))
    assert len(relationship.customer_relationship("C0002", analyst)["cases"]) == 1
    assert len(service.list_customers()) == 20
    with service._db() as con:
        assert con.execute("SELECT status FROM telephony_calls WHERE call_id='reset-call'").fetchone()[0] == call_state
