"""Staff relationship operations backed by the durable local CRM service."""
from __future__ import annotations

from datetime import datetime, time, timezone
import json
import logging
import os
from urllib.parse import quote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st

from public_app.repository import DemoError
from public_app.ui.relationship import CATEGORIES, CASE_STATUSES, LANGUAGES, PRIORITIES, SEGMENTS, csv_template, parse_import, source_template
from samvaad.models import ActionError, DEMO_ACTORS

logger = logging.getLogger("samvaad.relationship_ui")


def invitation_origin(service) -> str:
    """Use a trusted deployment setting; never derive a token URL from headers."""
    raw = os.getenv("SAMVAAD_RELATIONSHIP_API_ORIGIN") or os.getenv("SAMVAAD_PUBLIC_BASE_URL") or getattr(service, "public_base_url", "http://127.0.0.1:8000")
    try:
        parsed = urlsplit(raw)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError
        if parsed.scheme == "http" and not local:
            raise ValueError
        # Validate the port rather than allowing a malformed configured URL to
        # be printed with a private capability token.
        parsed.port
        return f"{parsed.scheme}://{parsed.netloc}"
    except (TypeError, ValueError) as error:
        raise ActionError("PORTAL_ORIGIN_INVALID", "Configure a trusted HTTPS portal origin, or a localhost origin for local testing.") from error


def _error(error):
    if isinstance(error, (ActionError, DemoError)):
        st.error(str(error))
    else:
        logger.error("Relationship UI request failed: %s", type(error).__name__)
        st.error("The relationship request could not complete. Connection details remain private.")


def _key(scope):
    return st.session_state.setdefault("relationship_staff_intent_" + scope, uuid4().hex)


def _changed(message, on_change=None):
    st.session_state["relationship_staff_flash"] = message
    if on_change:
        on_change()
    st.rerun()


def _invite_result(result, service, scope):
    token = result.get("token")
    if token:
        link = invitation_origin(service) + "/portal/" + quote(token, safe="")
        st.session_state["relationship_staff_link_" + scope] = link
        st.session_state["relationship_staff_display_" + scope] = link
        st.session_state["relationship_staff_expiry_" + scope] = result.get("expires_at")
    else:
        st.info("This invitation already exists. Its private token is returned only when first issued; create a new invitation if the original link was lost.")


def _show_link(scope):
    link = st.session_state.get("relationship_staff_link_" + scope)
    if link:
        display_key = "relationship_staff_display_" + scope
        st.session_state.setdefault(display_key, link)
        st.text_input("Private customer capability link", value=None, disabled=True, key=display_key)
        st.caption("Treat this expiring link like a password. Share it only with the intended applicant or customer through your approved channel.")
        if st.session_state.get("relationship_staff_expiry_" + scope):
            st.caption("Expires: " + str(st.session_state["relationship_staff_expiry_" + scope]))
        if link.startswith("http://"):
            st.info("This is a local test link. A remotely accessible portal requires an HTTPS API deployment.")


def _onboarding(relationship, service, actor, on_change):
    st.subheader("A clear path from applicant to relationship")
    st.caption("Applicant intake → officer review → customer record. Onboarding creates no loan, offer or KYC verdict.")
    with st.expander("Invite an applicant to complete their own intake"):
        st.caption("The scoped intake link permits one application. It does not expose other customers or allow approvals.")
        if st.button("Create applicant intake link", key="relationship_staff_intake_invite"):
            try:
                invitation_origin(service)
                result = relationship.issue_onboarding_invite(actor, _key("intake_invite"))
                _invite_result(result, service, "intake")
            except Exception as error:
                _error(error)
        _show_link("intake")
        if st.session_state.get("relationship_staff_link_intake") and st.button("Prepare a new applicant intake invitation", key="relationship_staff_new_intake"):
            st.session_state.pop("relationship_staff_intent_intake_invite", None)
            st.session_state.pop("relationship_staff_link_intake", None)
            st.rerun()
    with st.form("relationship_staff_onboarding"):
        a, b = st.columns(2)
        with a:
            name = st.text_input("Customer full name", max_chars=120)
            city = st.text_input("Customer city", max_chars=100)
            segment = st.selectbox("Relationship segment", SEGMENTS)
            phone = st.text_input("Telephone number (optional, international format)", max_chars=16, placeholder="+ country code and number")
        with b:
            income = st.number_input("Declared monthly income (₹)", min_value=0.0, value=0.0, step=1000.0)
            language = st.selectbox("Customer language", LANGUAGES)
            email = st.text_input("Customer email (optional)", max_chars=254)
        calls = st.checkbox("Customer authorised service calls", value=False)
        marketing = st.checkbox("Customer authorised marketing", value=False)
        dnd = st.checkbox("Customer requested no contact", value=False)
        reference = st.text_input("Permission evidence reference", max_chars=500, placeholder="Required when calls or marketing are authorised")
        identity = st.checkbox("Officer attests identity review completed", value=False)
        documents = st.checkbox("Officer attests document review completed", value=False)
        st.caption("Attestations record a review outside this application. Identity verification and document authenticity are not automated here.")
        submit = st.form_submit_button("Submit onboarding for review", type="primary", disabled=actor.role not in {"ANALYST", "ADMIN"})
        if actor.role not in {"ANALYST", "ADMIN"}:
            st.caption("An intake analyst or administrator submits applications. Managers and credit reviewers use the review queue below.")
    if submit:
        try:
            payload = dict(full_name=name, city=city, segment=segment, monthly_income=income, preferred_language=language,
                phone=phone, email=email, consent_calls=calls, consent_marketing=marketing, dnd=dnd,
                consent_reference=reference, identity_review=identity, document_review=documents)
            relationship.submit_onboarding(payload, actor, _key("onboarding"))
            st.session_state.pop("relationship_staff_intent_onboarding", None)
            _changed("Onboarding saved. A manager must review it before a customer record is created.", on_change)
        except Exception as error:
            _error(error)
    applications = relationship.list_onboardings(actor)
    if applications:
        rows = []
        for application in applications:
            payload = application.get("payload", application)
            rows.append({"Name": payload.get("full_name"), "Status": application.get("status"),
                         "Customer ID": application.get("customer_id") or "Awaiting review", "Application": application.get("onboarding_id", application.get("application_id"))})
        st.dataframe(rows, hide_index=True, width="stretch")
    pending = [a for a in applications if a.get("status") in {"SUBMITTED", "PENDING_REVIEW"}]
    if pending:
        st.markdown("**Review pending onboarding**")
        if actor.role not in {"MANAGER", "ADMIN"}:
            st.info("A manager or administrator must approve or reject onboarding. This operator can submit applications.")
            return
        with st.form("relationship_staff_review"):
            selected = st.selectbox("Onboarding awaiting review", pending, format_func=lambda a: a.get("payload", a).get("full_name", "Application"))
            decision = st.radio("Onboarding decision", ["APPROVE", "REJECT"], horizontal=True)
            identity = st.checkbox("Reviewer confirms identity review completed", value=False)
            documents = st.checkbox("Reviewer confirms document review completed", value=False)
            note = st.text_input("Officer review note", max_chars=500)
            review = st.form_submit_button("Save onboarding decision")
        if review:
            try:
                oid = selected.get("onboarding_id", selected.get("application_id"))
                if decision == "APPROVE":
                    if not identity or not documents:
                        raise ActionError("REVIEW_CHECKLIST_REQUIRED", "Confirm both review attestations before approving the applicant.")
                    relationship.attest_onboarding(oid, identity, documents, note, actor)
                relationship.review_onboarding(oid, decision, note, actor)
                _changed("Onboarding decision saved. Approved relationships are available in Customer 360.", on_change)
            except Exception as error:
                _error(error)


def _sync(relationship, actor, on_change):
    st.subheader("Validate, preview, and apply source changes")
    st.caption("Import customers, loans, payments and interactions using stable source IDs and increasing source versions. Conflicting or invalid rows block the whole run.")
    if actor.role in {"MANAGER", "ADMIN"}:
        with st.expander("Link an existing customer to a source identity"):
            st.caption("An officer reviews this immutable mapping before loan-system records are attached. A name match cannot establish identity.")
            cid = _customer_picker(relationship.service, "relationship_staff_mapping_customer")
            with st.form("relationship_staff_mapping"):
                mapping_source = st.text_input("Source system ID", value="lending-crm", max_chars=80)
                source_customer = st.text_input("Stable source customer ID", max_chars=120)
                mapping_note = st.text_input("Reviewed mapping evidence", max_chars=500)
                mapped = st.form_submit_button("Save reviewed source identity", disabled=cid is None)
            if mapped:
                try:
                    relationship.link_source_customer(mapping_source, source_customer, cid, actor,
                        _key("mapping_" + mapping_source + "_" + source_customer), mapping_note)
                    _changed("Reviewed source identity linked. Loan and interaction imports can now reference this same customer.", on_change)
                except Exception as error:
                    _error(error)
    a, b = st.columns(2)
    a.download_button("Download onboarding CSV template", csv_template(), "samvaad-customer-source.csv", "text/csv", key="relationship_staff_csv")
    b.download_button("Download full relationship JSON example", json.dumps(source_template(), indent=2), "samvaad-fictional-relationship-source.json", "application/json", key="relationship_staff_json")
    st.caption("CSV covers customer records. The JSON example links fictional customer, loan, payment and interaction records; replace its demonstration data with reviewed source exports for private operational imports.")
    source = st.text_input("Operational source ID", value="lending-crm", max_chars=80, key="relationship_staff_source")
    upload = st.file_uploader("Customer data CSV or JSON · up to 1 MB / 200 records", type=["csv", "json"], max_upload_size=1, key="relationship_staff_upload")
    if st.button("Preview and validate import", disabled=upload is None or actor.role not in {"ANALYST", "ADMIN"}, type="primary", key="relationship_staff_preview"):
        try:
            records = parse_import(upload.getvalue(), upload.name)
            digest = sha256_bytes(upload.getvalue())
            run = relationship.preview_sync(source, records, actor, _key("sync_" + source + "_" + digest))
            st.session_state["relationship_staff_run"] = run["run_id"]
            _changed("Source data preview saved. Review the results before applying it.")
        except Exception as error:
            _error(error)
    selected = st.session_state.get("relationship_staff_run")
    run = relationship.sync_run(selected, actor) if selected else None
    if run:
        st.write("Preview status: **" + run.get("status", "Unknown") + "**")
        summary = run.get("summary", {})
        if summary:
            st.dataframe([{"Measure": str(k).replace("_", " ").title(), "Count": v} for k, v in summary.items() if isinstance(v, (int, float))], hide_index=True, width="stretch")
        errors = run.get("errors") or []
        if errors:
            st.error("Nothing will be applied until every rejected row and version conflict is resolved.")
            st.dataframe(errors, hide_index=True, width="stretch")
        consent = st.checkbox("Apply this complete validated run to the operational relationship database", key="relationship_staff_commit_permission")
        if st.button("Apply validated source run", disabled=run.get("status") != "VALIDATED" or not consent, key="relationship_staff_commit"):
            try:
                relationship.commit_sync(run["run_id"], actor)
                _changed("Source changes applied atomically. Customer 360 now reads the updated operational records.", on_change)
            except Exception as error:
                _error(error)
    runs = relationship.list_sync_runs(actor)
    if runs:
        st.markdown("**Source run history**")
        st.dataframe([{k: r.get(k) for k in ("source", "status", "run_id", "created_at", "committed_at")} for r in runs], hide_index=True, width="stretch")
    with st.expander("Inspect a customer's source identities and versions"):
        cid = _customer_picker(relationship.service, "relationship_staff_source_customer")
        if cid:
            sources = relationship.customer_relationship(cid, actor).get("sources", [])
            if sources:
                st.dataframe([{k: row.get(k) for k in ("source", "record_type", "source_record_id", "source_version", "local_id", "updated_at")} for row in sources], hide_index=True, width="stretch")
            else:
                st.caption("This customer has no source identities yet. Use a reviewed mapping or apply a validated source import.")
    st.caption("A successful local import is not a Snowflake publish. Use the controlled publisher and configured scheduler to synchronize the analytics snapshot.")


def sha256_bytes(data):
    from hashlib import sha256
    return sha256(data).hexdigest()


def _customer_picker(service, key):
    customers = service.list_customers()
    if not customers:
        st.info("Approve onboarding or import a customer before managing relationships.")
        return None
    indexed = {c["customer_id"]: c for c in customers}
    return st.selectbox("Operational relationship customer", list(indexed), format_func=lambda cid: f'{indexed[cid]["full_name"]} · {cid}', key=key)


def _cases(relationship, service, actor, on_change):
    st.subheader("Own each request through resolution")
    cid = _customer_picker(service, "relationship_staff_case_customer")
    if cid is None:
        return
    with st.form("relationship_staff_case"):
        subject = st.text_input("Case subject", max_chars=160)
        description = st.text_area("Case description", max_chars=2000)
        a, b = st.columns(2)
        with a:
            category = st.selectbox("Service category", CATEGORIES)
            priority = st.selectbox("Urgency", PRIORITIES, index=1)
        with b:
            owners = [user for user, member in DEMO_ACTORS.items() if member.role != "AUTOMATION"]
            owner = st.selectbox("Assigned relationship officer", owners, index=owners.index(actor.user_id) if actor.user_id in owners else 0)
            due = st.date_input("Target resolution date")
            due_enabled = st.checkbox("Record target resolution date", value=False)
        submit = st.form_submit_button("Save customer case", type="primary")
    if submit:
        try:
            due_at = datetime.combine(due, time(17), ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc).isoformat() if due_enabled else None
            payload = dict(subject=subject, description=description, category=category, priority=priority, owner=owner, due_at=due_at)
            relationship.add_case(cid, payload, actor, _key("case_" + cid))
            st.session_state.pop("relationship_staff_intent_case_" + cid, None)
            _changed("Customer case saved with its owner and priority.", on_change)
        except Exception as error:
            _error(error)
    view = relationship.customer_relationship(cid, actor)
    cases = view.get("cases", [])
    if not cases:
        st.caption("No service cases recorded for this customer yet.")
        return
    st.dataframe([{k: case.get(k) for k in ("subject", "category", "priority", "status", "owner", "due_at", "case_id")} for case in cases], hide_index=True, width="stretch")
    with st.form("relationship_staff_case_progress"):
        case = st.selectbox("Customer case to update", cases, format_func=lambda row: str(row.get("subject")) + " · " + str(row.get("status")))
        status = st.selectbox("Resolution status", CASE_STATUSES)
        note = st.text_input("Case progress note", max_chars=500)
        save = st.form_submit_button("Save progress and status")
    if save:
        try:
            relationship.update_case(case["case_id"], status, note, actor)
            _changed("Case progress saved.", on_change)
        except Exception as error:
            _error(error)


def _portal(relationship, service, actor):
    st.subheader("Give the customer a scoped self-service portal")
    st.caption("Customers can see their own relationship requests and withdraw contact permission. The link does not expose loan balances or allow financial approvals.")
    cid = _customer_picker(service, "relationship_staff_portal_customer")
    if cid is None:
        return
    try:
        invitation_origin(service)
    except ActionError as error:
        st.warning(error.message)
        return
    if st.button("Create private customer portal link", type="primary", key="relationship_staff_portal_invite"):
        try:
            result = relationship.issue_portal_invite(cid, actor, _key("portal_" + cid))
            _invite_result(result, service, cid)
        except Exception as error:
            _error(error)
    _show_link(cid)
    if st.session_state.get("relationship_staff_link_" + cid) and st.button("Prepare a new customer invitation", key="relationship_staff_new_portal"):
        st.session_state.pop("relationship_staff_intent_portal_" + cid, None)
        st.session_state.pop("relationship_staff_link_" + cid, None)
        st.rerun()


def render_staff_relationship(service, actor, on_change=None):
    """Persistent staff UI; backend authorization remains authoritative."""
    from samvaad.relationship import RelationshipService
    st.subheader("Customer relationship operations")
    st.caption("Onboarding, data reconciliation, service ownership and customer self-service in one guided workspace.")
    if not hasattr(service, "db_path"):
        st.info("Relationship operations require the operational API/database deployment. This Snowflake analytics view remains read-only for onboarding and imports.")
        return
    try:
        relationship = RelationshipService(service)
        status = relationship.status(actor)
        a, b, c = st.columns(3)
        a.metric("Operational customers", status.get("customers", 0))
        b.metric("Awaiting onboarding review", status.get("pending_onboardings", 0))
        c.metric("Awaiting analytics publish", status.get("pending_exports", 0))
        st.caption("Operational changes are persistent locally and queued for a controlled analytics publisher. A scheduled cloud synchronization is enabled separately.")
        flash = st.session_state.pop("relationship_staff_flash", None)
        if flash:
            st.success(flash)
        mode = st.radio("Relationship operations workspace", ["Onboarding", "Data sync", "Relationship cases", "Customer portal"], horizontal=True, key="relationship_staff_workspace")
        if mode == "Onboarding":
            _onboarding(relationship, service, actor, on_change)
        elif mode == "Data sync":
            _sync(relationship, actor, on_change)
        elif mode == "Relationship cases":
            _cases(relationship, service, actor, on_change)
        else:
            _portal(relationship, service, actor)
    except Exception as error:
        _error(error)
