"""Visit relationship records remain scoped across the complete public app."""
from copy import deepcopy
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from cloud.config import WORKSPACE
from public_app import repository as public
from public_app import security as public_security
from public_app.relationship_repository import VisitRelationshipReader
from public_app.repository import DemoError, SnapshotReader
from public_app.ui.relationship import PublicRelationshipSandbox
from test_public_cloud import Connection


class MemoryBase:
    """Deliberately returns shared objects, exposing accidental cross-visit writes."""
    is_live = False

    def __init__(self):
        snapshot = SnapshotReader(WORKSPACE / "public_app/synthetic_snapshot.json")
        self.reference = snapshot.reference
        self.views = {c["customer_id"]: snapshot.customer360(c["customer_id"]) for c in snapshot.customers()}
        self.list = [view["customer"] for view in self.views.values()]

    def customers(self):
        return self.list

    def customer360(self, cid):
        if cid not in self.views:
            raise DemoError("Unknown snapshot customer.")
        return self.views[cid]

    def source_status(self):
        return {"stale": False, "daily_statement_limit": 64}

    def rows(self, *_args, **_kwargs):
        pytest.fail("Relationship views must never issue database queries.")


def add_relationship(hub, name="Visit Customer Demo"):
    application = hub.submit({"full_name": name, "city": "Pune", "segment": "SALARIED", "monthly_income": 45000,
        "preferred_language": "English", "identity_review": True, "document_review": True,
        "consent_calls": False, "consent_marketing": False, "dnd": False})
    return hub.review(application["application_id"], "APPROVE", "Fictional review")["customer_id"]


def test_new_relationship_is_visible_in_360_picker_and_portfolio_only_in_own_visit():
    base = MemoryBase()
    one = PublicRelationshipSandbox({}, base.customers())
    two = PublicRelationshipSandbox({}, base.customers())
    first, second = VisitRelationshipReader(base, one), VisitRelationshipReader(base, two)
    cid = add_relationship(one)
    assert len(first.customers()) == len(first.portfolio_profiles()) == 21
    assert len(second.customers()) == len(second.portfolio_profiles()) == 20
    view = first.customer360(cid)
    assert view["rehearsal"] and view["customer"]["full_name"] == "Visit Customer Demo"
    assert view["loans"] == [] and view["metrics"]["active_loans"] == 0
    assert view["decision"]["action_code"] == "NO_ACTION"
    with pytest.raises(DemoError):
        second.customer360(cid)


def test_seeded_customer_permission_reduction_recomputes_policy_without_base_mutation():
    base = MemoryBase()
    before = deepcopy(base.views)
    one = PublicRelationshipSandbox({}, base.customers())
    two = PublicRelationshipSandbox({}, base.customers())
    first, second = VisitRelationshipReader(base, one), VisitRelationshipReader(base, two)
    assert first.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    one.opt_out("C0003")
    changed = first.customer360("C0003")
    assert changed["rehearsal"] and changed["decision"]["action_code"] == "NO_ACTION"
    listed = next(c for c in first.customers() if c["customer_id"] == "C0003")
    assert listed["dnd"] and not listed["consent_calls"]
    assert second.customer360("C0003")["decision"]["action_code"] == "TOPUP_PREAPPROVAL_CALL"
    assert base.views == before
    changed["customer"]["full_name"] = "Mutated returned copy"
    assert first.customer360("C0003")["customer"]["full_name"] != "Mutated returned copy"


def test_seeded_hardship_request_is_visit_evidence_and_suppresses_growth_without_financial_writes():
    base = MemoryBase()
    before = deepcopy(base.views["C0003"])
    hub = PublicRelationshipSandbox({}, base.customers())
    reader = VisitRelationshipReader(base, hub)
    case = hub.case("C0003", "Repayment support", "Please discuss support options.", "HARDSHIP")
    view = reader.customer360("C0003")
    assert view["rehearsal"] and view["metrics"]["hardship_flag"]
    assert view["decision"]["action_code"] != "TOPUP_PREAPPROVAL_CALL"
    assert case["case_id"] in {i["interaction_id"] for i in view["interactions"]}
    assert view["loans"] == before["loans"] and view["payments"] == before["payments"]
    assert base.views["C0003"] == before
    hub.update_case(case["case_id"], "RESOLVED", "Officer completed the support request")
    after_resolution = reader.customer360("C0003")
    assert after_resolution["metrics"]["hardship_flag"] is True
    assert after_resolution["decision"]["action_code"] != "TOPUP_PREAPPROVAL_CALL"
    retained = next(i for i in after_resolution["interactions"] if i["interaction_id"] == case["case_id"])
    assert retained["ts"] == case["created_at"]


def test_decision_answer_is_scoped_to_new_customer_and_never_enables_queries():
    base = MemoryBase()
    hub = PublicRelationshipSandbox({}, base.customers())
    first = add_relationship(hub, "First Visit Demo")
    second = add_relationship(hub, "Second Visit Demo")
    reader = VisitRelationshipReader(base, hub)
    answer = reader.answer(first, "Summarize the current relationship")
    assert answer["provider"].startswith("Visit-local relationship rehearsal")
    assert "First Visit Demo" in answer["answer"] and "Second Visit Demo" not in answer["answer"]
    for question in ("Summarize " + second, "Tell me about Second Visit Demo", "Summarize C0002"):
        with pytest.raises(DemoError):
            reader.answer(first, question)
    assert reader.answer(first, "Approve an offer")["provider"] == "Policy boundary"
    with pytest.raises(DemoError):
        reader.answer(first, "Next best action", cortex=True)
    with pytest.raises(DemoError):
        reader.rows("SELECT * FROM customers")


def test_untouched_snapshot_answers_keep_truthful_provider_and_source_status():
    base = MemoryBase()
    hub = PublicRelationshipSandbox({}, base.customers())
    reader = VisitRelationshipReader(base, hub)
    assert reader.source_status() == base.source_status()
    assert reader.is_live is False
    assert reader.answer("C0001", "Why support?")["provider"].startswith("Bundled synthetic snapshot")
    base.is_live = True
    assert reader.answer("C0001", "Why support?")["provider"].startswith("Protected Snowflake snapshot")


@pytest.fixture
def website(monkeypatch, tmp_path):
    st.cache_data.clear()
    st.cache_resource.clear()
    connection = Connection()
    source = public.PublicReader(public.ReadSession(connection))
    monkeypatch.setattr(st, "secrets", {"snowflake": {}})
    guard = public_security.PublicGuard
    monkeypatch.setattr(public_security, "PublicGuard", lambda: guard(tmp_path / "guard.db"))
    monkeypatch.setattr(public, "connect_reader", lambda *_a, **_k: source)
    yield AppTest.from_file(str(WORKSPACE / "public_app/streamlit_app.py"), default_timeout=15), connection
    st.cache_data.clear()
    st.cache_resource.clear()


def widget(items, label):
    return next(item for item in items if item.label == label)


def run_workspace(app, name):
    # AppTest represents tabs as static blocks and cannot select a tracked tab.
    # Supply its frontend selection explicitly on each widget interaction; the
    # separate browser check exercises the real tracked-tab interaction.
    app.session_state["workspace_tabs"] = name
    return app.run()


def test_complete_website_onboarding_reaches_main_360_and_evidence_without_extra_sql(website):
    app, connection = website
    app.run()
    assert not app.exception and len(app.tabs) == 6
    initial_reads = len(connection.calls)
    app.session_state["workspace_tabs"] = "Customer hub"
    app.run()
    widget(app.text_input, "Fictional customer name").set_value("Integrated Portal Demo")
    widget(app.checkbox, "Identity review attested by an officer").check()
    widget(app.checkbox, "Document review attested by an officer").check()
    widget(app.button, "Submit fictional application").click()
    run_workspace(app, "Customer hub")
    widget(app.button, "Save fictional review").click()
    run_workspace(app, "Customer hub")
    assert not app.exception
    cid = next(iter(app.session_state["public_relationship_state"]["customers"]))
    app.session_state["workspace_tabs"] = "Customer 360"
    widget(app.selectbox, "Customer").select(cid).run()
    assert not app.exception
    assert any("Integrated Portal Demo" in item.value for item in app.markdown)
    assert any("Visit-only relationship" in item.value for item in app.info)
    assert widget(app.button, "Add to review queue").disabled
    app.session_state["workspace_tabs"] = "Evidence desk"
    app.run()
    widget(app.text_input, "Question").set_value("Why is this next step recommended?")
    widget(app.button, "Find the evidence").click().run()
    assert not app.exception
    assert app.session_state["public_answer"]["provider"].startswith("Visit-local relationship rehearsal")
    assert len(connection.calls) == initial_reads


def test_complete_website_portal_optout_blocks_review_and_call_for_same_visit(website):
    app, connection = website
    app.run()
    initial_reads = len(connection.calls)
    app.session_state["workspace_tabs"] = "Customer hub"
    app.run()
    widget(app.radio, "Customer hub workspace").set_value("Customer portal")
    run_workspace(app, "Customer hub")
    widget(app.selectbox, "Preview as fictional customer").select("C0003")
    run_workspace(app, "Customer hub")
    widget(app.button, "Rehearse withdrawing all contact permission").click()
    run_workspace(app, "Customer hub")
    app.session_state["workspace_tabs"] = "Customer 360"
    widget(app.selectbox, "Customer").select("C0003").run()
    assert not app.exception and widget(app.button, "Add to review queue").disabled
    app.session_state["workspace_tabs"] = "Call studio"
    app.run()
    assert not app.exception and widget(app.button, "Start conversation rehearsal").disabled
    assert len(connection.calls) == initial_reads
