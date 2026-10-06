"""Relationship portal UI journeys and anonymous session isolation."""
from copy import deepcopy
import json

import pytest
from streamlit.testing.v1 import AppTest

from app.relationship_ui import invitation_origin
from public_app.repository import DemoError
from public_app.ui.relationship import PublicRelationshipSandbox, csv_template, customer_template, parse_import, source_template
from samvaad.models import ActionError


def applicant(**changes):
    return {"full_name": "Asha Demo", "city": "Pune", "segment": "SALARIED", "monthly_income": 45000,
            "preferred_language": "English", "consent_calls": False, "consent_marketing": False, "dnd": False,
            "identity_review": True, "document_review": True, "consent_reference": "", **changes}


def button(app, label):
    return next(item for item in app.button if item.label == label)


def widget(items, label):
    return next(item for item in items if item.label == label)


def test_template_csv_round_trip_has_typed_numeric_and_false_values():
    records = parse_import(csv_template().encode(), "source.csv")
    assert records == customer_template()
    run = PublicRelationshipSandbox().preview("demo-crm", records)
    assert run["status"] == "VALIDATED" and run["summary"]["new"] == 1


def test_full_relationship_json_example_reconciles_four_record_types_into_one_360():
    records = parse_import(json.dumps(source_template()).encode(), "source.json")
    hub = PublicRelationshipSandbox()
    run = hub.preview("fictional-full-source", records)
    assert run["status"] == "VALIDATED" and run["summary"]["new"] == 4
    hub.commit(run["run_id"])
    assert len(hub.customers()) == 1
    cid = hub.customers()[0]["customer_id"]
    view = hub.customer360(cid)
    assert len(view["loans"]) == len(view["payments"]) == len(view["interactions"]) == 1
    assert view["metrics"]["total_outstanding"] == 160000
    assert view["metrics"]["on_time_ratio"] == 1
    assert view["customer"]["consent_calls"] is False and view["customer"]["consent_marketing"] is False
    assert view["decision"]["action_code"] == "NO_ACTION"
    repeat = hub.preview("fictional-full-source", records)
    assert repeat["status"] == "VALIDATED" and repeat["summary"]["unchanged"] == 4


@pytest.mark.parametrize("body,name", [
    (b"[{\"record_type\": \"customer\", \"record_type\": \"loan\"}]", "data.json"),
    (b"[{\"monthly_income\": NaN}]", "data.json"),
    (b"[{\"monthly_income\": Infinity}]", "data.json"),
    (b"{}", "data.json"),
    (b"[]", "data.json"),
    (b"source_version,source_version\n1,2", "data.csv"),
    (b"consent_calls\nprobably", "data.csv"),
    (b"source_version\n1.5", "data.csv"),
    (b"monthly_income\nNaN", "data.csv"),
    (b"a,b\n1", "data.csv"),
    (b"a,b\n1,2,3", "data.csv"),
    (b"anything", "data.txt"),
])
def test_import_rejects_ambiguous_or_unbounded_values(body, name):
    with pytest.raises(DemoError):
        parse_import(body, name)


def test_import_record_and_file_limits():
    with pytest.raises(DemoError):
        parse_import(b"x" * 1_000_001, "data.csv")
    with pytest.raises(DemoError):
        parse_import(json.dumps([{}] * 201).encode(), "data.json")
    with pytest.raises(DemoError):
        parse_import(("full_name\n" + "Demo\n" * 201).encode(), "data.csv")


def test_new_relationship_is_reviewed_isolated_and_has_no_fabricated_loan():
    first, second = PublicRelationshipSandbox(), PublicRelationshipSandbox()
    application = first.submit(applicant())
    approved = first.review(application["application_id"], "APPROVE", "Fictional officer reviewed")
    cid = approved["customer_id"]
    assert first.contains(cid) and not second.contains(cid)
    view = first.customer360(cid)
    assert view["customer"]["full_name"] == "Asha Demo" and view["rehearsal"] is True
    assert view["loans"] == [] and view["payments"] == []
    assert view["decision"]["action_code"] == "NO_ACTION"
    with pytest.raises(DemoError):
        second.review(application["application_id"], "APPROVE", "Other visit")
    with pytest.raises(DemoError):
        second.customer360(cid)


def test_public_onboarding_never_accepts_or_stores_contact_details():
    hub = PublicRelationshipSandbox()
    for contact in ({"phone": "+12025550101"}, {"email": "person@example.invalid"}):
        with pytest.raises(DemoError):
            hub.submit(applicant(**contact))
    application = hub.submit(applicant(consent_calls=True, consent_reference="Fictional recorded permission"))
    assert application["payload"]["phone"] == application["payload"]["email"] == ""
    assert "+12025550100" not in json.dumps(hub.state)
    with pytest.raises(DemoError):
        hub.submit(applicant(consent_calls=True))


def test_public_review_attestations_are_required_and_rejection_creates_no_customer():
    hub = PublicRelationshipSandbox()
    pending = hub.submit(applicant(document_review=False))
    with pytest.raises(DemoError):
        hub.review(pending["application_id"], "APPROVE", "Not reviewed")
    rejected = hub.review(pending["application_id"], "REJECT", "Documents incomplete")
    assert rejected["status"] == "REJECTED" and hub.customers() == []


def test_source_versions_conflicts_and_stale_preview_block_without_partial_apply():
    hub = PublicRelationshipSandbox()
    initial = hub.preview("crm", customer_template())
    hub.commit(initial["run_id"])
    records = deepcopy(customer_template())
    records[0].update(source_version=2, monthly_income=46000)
    older = hub.preview("crm", records)
    records[0].update(source_version=3, monthly_income=47000)
    later = hub.preview("crm", records)
    hub.commit(later["run_id"])
    before = deepcopy(hub.state)
    with pytest.raises(DemoError):
        hub.commit(older["run_id"])
    assert hub.state == before
    conflict = hub.preview("crm", [{**records[0], "monthly_income": 48000}])
    assert conflict["status"] == "INVALID"
    with pytest.raises(DemoError):
        hub.commit(conflict["run_id"])


def test_source_import_cannot_grant_contact_permission_or_bypass_required_mapping():
    hub = PublicRelationshipSandbox()
    records = [{**customer_template()[0], "consent_marketing": True}]
    run = hub.preview("crm", records)
    hub.commit(run["run_id"])
    customer = hub.customers()[0]
    assert customer["consent_calls"] is False and customer["consent_marketing"] is False
    loan = {"record_type": "loan", "source_record_id": "l-1", "source_version": 1,
        "customer_ref": customer["customer_id"], "product": "PERSONAL_LOAN", "principal": 100000,
        "outstanding": 75000, "interest_rate": 12, "emi": 5000, "relationship_months": 12,
        "current_dpd": 0, "status": "ACTIVE", "disbursed_on": "2025-10-01"}
    assert hub.preview("crm", [loan])["status"] == "INVALID"


def test_onboarding_source_mapping_joins_all_four_record_types_into_customer360():
    hub = PublicRelationshipSandbox()
    pending = hub.submit(applicant(consent_calls=True, consent_reference="Fictional opt-in"))
    cid = hub.review(pending["application_id"], "APPROVE", "Fictional reviewed")["customer_id"]
    hub.link_source_customer("crm", "customer-1", cid, "Reviewed fictional identity")
    records = [
        {"record_type": "loan", "source_record_id": "loan-1", "source_version": 1,
         "customer_ref": "customer-1", "principal": 100000, "outstanding": 75000, "interest_rate": 12,
         "emi": 5000, "relationship_months": 12, "current_dpd": 8, "status": "ACTIVE", "disbursed_on": "2025-10-01"},
        {"record_type": "payment", "source_record_id": "payment-1", "source_version": 1,
         "loan_ref": "loan-1", "due_date": "2026-09-01", "paid_date": "2026-09-01", "amount_due": 5000, "amount_paid": 5000, "status": "PAID"},
        {"record_type": "interaction", "source_record_id": "interaction-1", "source_version": 1,
         "customer_ref": "customer-1", "channel": "CHAT", "text": "Customer: I lost my job and need help paying my EMI.",
         "ts": "2026-10-06T10:00:00+00:00"},
    ]
    run = hub.preview("crm", records)
    assert run["status"] == "VALIDATED"
    hub.commit(run["run_id"])
    view = hub.customer360(cid)
    assert view["metrics"]["total_outstanding"] == 75000 and view["metrics"]["dpd"] == 8
    assert len(view["loans"]) == len(view["payments"]) == len(view["interactions"]) == 1
    assert len(hub.customers()) == 1
    hub.opt_out(cid)
    assert hub.customer360(cid)["decision"]["action_code"] == "NO_ACTION"


def test_source_mapping_and_case_scope_cannot_move_between_customers():
    hub = PublicRelationshipSandbox()
    ids = []
    for name in ("Asha Demo", "Bela Demo"):
        pending = hub.submit(applicant(full_name=name))
        ids.append(hub.review(pending["application_id"], "APPROVE", "Reviewed")["customer_id"])
    hub.link_source_customer("crm", "one", ids[0], "Reviewed")
    with pytest.raises(DemoError):
        hub.link_source_customer("crm", "one", ids[1], "Move identity")
    case = hub.case(ids[0], "Callback", "Fictional service request")
    hub.update_case(case["case_id"], "IN_PROGRESS", "Officer owns request")
    assert hub.state["cases"][0]["status"] == "IN_PROGRESS"
    with pytest.raises(DemoError):
        PublicRelationshipSandbox().update_case(case["case_id"], "CLOSED", "Other visit")


def test_visit_hardship_and_complaint_cases_are_attributed_decision_evidence():
    hub = PublicRelationshipSandbox()
    pending = hub.submit(applicant(consent_calls=True, consent_reference="Fictional permission"))
    cid = hub.review(pending["application_id"], "APPROVE", "Reviewed")["customer_id"]
    case = hub.case(cid, "Support request", "I need to discuss repayment support.", "HARDSHIP")
    view = hub.customer360(cid)
    assert view["metrics"]["hardship_flag"] is True
    assert view["interactions"][0]["interaction_id"] == case["case_id"]
    assert view["interactions"][0]["intent_source"] == "Fictional customer service-case category"
    assert view["loans"] == []
    hub.update_case(case["case_id"], "RESOLVED", "Officer completed support review")
    assert hub.customer360(cid)["metrics"]["hardship_flag"] is True
    assert hub.customer360(cid)["interactions"][0]["ts"] == case["created_at"]
    complaint = hub.case(cid, "Rate complaint", "Please review my service request.", "COMPLAINT")
    assert hub.customer360(cid)["metrics"]["churn_risk"] >= .2
    assert complaint["case_id"] in {item["interaction_id"] for item in hub.customer360(cid)["interactions"]}


def test_complaint_category_does_not_hide_hardship_in_the_actual_case_text():
    hub = PublicRelationshipSandbox()
    pending = hub.submit(applicant())
    cid = hub.review(pending["application_id"], "APPROVE", "Reviewed")["customer_id"]
    hub.case(cid, "Poor service", "I lost my job and cannot afford repayment.", "COMPLAINT")
    assert hub.customer360(cid)["metrics"]["hardship_flag"] is True
    assert hub.customer360(cid)["interactions"][0]["intent"] == "financial hardship"


@pytest.mark.parametrize("origin", ["http://example.org", "https://example.org/portal", "https://user:pass@example.org", "https://example.org?secret=x", "https://example.org#fragment", "https://example.org:bad"])
def test_private_portal_origin_is_trusted_https_or_local_only(monkeypatch, origin):
    monkeypatch.setenv("SAMVAAD_RELATIONSHIP_API_ORIGIN", origin)
    with pytest.raises(ActionError):
        invitation_origin(object())


def test_private_portal_origin_can_be_https_or_localhost(monkeypatch):
    monkeypatch.setenv("SAMVAAD_RELATIONSHIP_API_ORIGIN", "https://portal.example.invalid/")
    assert invitation_origin(object()) == "https://portal.example.invalid"
    monkeypatch.setenv("SAMVAAD_RELATIONSHIP_API_ORIGIN", "http://127.0.0.1:8000")
    assert invitation_origin(object()) == "http://127.0.0.1:8000"


PUBLIC_APP = '''
from public_app.ui.relationship import render_relationship_hub
class Reader:
    def customers(self):
        return [{"customer_id":"C0001", "full_name":"Seeded Demo", "city":"Pune", "preferred_language":"English",
                 "consent_calls":True, "consent_marketing":False, "dnd":False}]
render_relationship_hub(Reader())
'''


def test_public_ui_onboarding_review_customer_portal_and_other_visit_isolation():
    app = AppTest.from_string(PUBLIC_APP).run(timeout=20)
    assert not app.exception
    assert not any("phone" in item.label.lower() or "email" in item.label.lower() for item in app.text_input)
    widget(app.checkbox, "Identity review attested by an officer").check()
    widget(app.checkbox, "Document review attested by an officer").check()
    button(app, "Submit fictional application").click().run()
    assert not app.exception
    button(app, "Save fictional review").click().run()
    assert not app.exception
    state = app.session_state["public_relationship_state"]
    assert len(state["customers"]) == 1
    widget(app.radio, "Customer hub workspace").set_value("Customer portal").run()
    widget(app.selectbox, "Preview as fictional customer").set_value(next(iter(state["customers"]))).run()
    button(app, "Submit self-service request").click().run()
    assert not app.exception and len(app.session_state["public_relationship_state"]["cases"]) == 1
    other = AppTest.from_string(PUBLIC_APP).run()
    assert other.session_state["public_relationship_state"]["customers"] == {}
    assert other.session_state["public_relationship_state"]["cases"] == []


def test_public_ui_sample_import_requires_explicit_apply_and_has_visible_run_status():
    app = AppTest.from_string(PUBLIC_APP).run()
    widget(app.radio, "Customer hub workspace").set_value("Data sync").run()
    button(app, "Preview sample import").click().run()
    assert not app.exception
    assert app.session_state["public_relationship_state"]["customers"] == {}
    assert button(app, "Apply rehearsal import").disabled
    widget(app.checkbox, "Apply these fictional records to this visit only").check().run()
    button(app, "Apply rehearsal import").click().run()
    assert not app.exception and len(app.session_state["public_relationship_state"]["customers"]) == 1
    assert app.session_state["public_relationship_state"]["runs"][0]["status"] == "COMMITTED"


def test_staff_ui_persists_reviewed_onboarding_and_owned_case(tmp_path):
    source = f'''
import streamlit as st
from app.relationship_ui import render_staff_relationship
from samvaad.service import LocalService
from samvaad.models import DEMO_ACTORS
service = LocalService({str(tmp_path / "staff.db")!r}, seed=False)
operator = st.sidebar.selectbox("Test operator", ["meera", "arjun", "demo-admin"])
render_staff_relationship(service, DEMO_ACTORS[operator])
'''
    app = AppTest.from_string(source).run(timeout=20)
    widget(app.text_input, "Customer full name").set_value("Staff Journey Demo")
    widget(app.text_input, "Customer city").set_value("Pune")
    button(app, "Submit onboarding for review").click().run()
    assert not app.exception
    widget(app.selectbox, "Test operator").set_value("arjun").run()
    widget(app.checkbox, "Reviewer confirms identity review completed").check()
    widget(app.checkbox, "Reviewer confirms document review completed").check()
    widget(app.text_input, "Officer review note").set_value("Officer reviewed fictional identity and documents")
    button(app, "Save onboarding decision").click().run()
    assert not app.exception
    widget(app.radio, "Relationship operations workspace").set_value("Relationship cases").run()
    widget(app.text_input, "Case subject").set_value("Support follow-up")
    widget(app.text_area, "Case description").set_value("Customer requests a helpful officer callback.")
    button(app, "Save customer case").click().run()
    assert not app.exception
    from samvaad.relationship import RelationshipService
    from samvaad.service import LocalService
    from samvaad.models import DEMO_ACTORS
    service = LocalService(tmp_path / "staff.db", seed=False)
    customers = service.list_customers()
    assert len(customers) == 1
    view = RelationshipService(service).customer_relationship(customers[0]["customer_id"], DEMO_ACTORS["arjun"])
    assert view["cases"][0]["owner"] == "arjun" and view["cases"][0]["status"] == "OPEN"
    assert view["customer360"]["loans"] == []


def test_staff_ui_issues_once_scoped_intake_and_customer_invites(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMVAAD_RELATIONSHIP_API_ORIGIN", "http://127.0.0.1:8000")
    source = f'''
from app.relationship_ui import render_staff_relationship
from samvaad.service import LocalService
from samvaad.models import DEMO_ACTORS
service = LocalService({str(tmp_path / "invites.db")!r})
render_staff_relationship(service, DEMO_ACTORS["meera"])
'''
    app = AppTest.from_string(source).run(timeout=20)
    button(app, "Create applicant intake link").click().run()
    assert not app.exception
    intake_link = app.session_state["relationship_staff_link_intake"]
    from samvaad.relationship import RelationshipService
    from samvaad.service import LocalService
    relationship = RelationshipService(LocalService(tmp_path / "invites.db"))
    intake = relationship.portal_view(intake_link.rsplit("/", 1)[1])
    assert intake["purpose"] == "ONBOARDING"
    widget(app.radio, "Relationship operations workspace").set_value("Customer portal").run()
    button(app, "Create private customer portal link").click().run()
    assert not app.exception
    cid = widget(app.selectbox, "Operational relationship customer").value
    customer_link = app.session_state["relationship_staff_link_" + cid]
    portal = relationship.portal_view(customer_link.rsplit("/", 1)[1])
    assert portal["purpose"] == "CUSTOMER" and portal["customer_id"] == cid
    assert "loans" not in portal
