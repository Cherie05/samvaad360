"""Visit-local customer relationship rehearsal for the anonymous public website.

The operational service owns actual onboarding and imports. This module keeps
fictional exercises inside the visitor's session and never opens a database.
"""
from __future__ import annotations

import csv
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import math
from uuid import uuid4

import streamlit as st

from public_app.repository import DemoError

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_RECORDS = 200
SEGMENTS = ["SALARIED", "SELF_EMPLOYED", "OTHER"]
LANGUAGES = ["English", "Hindi", "Tamil", "Telugu", "Kannada", "Malayalam", "Marathi", "Bengali"]
CATEGORIES = ["SERVICE", "COMPLAINT", "HARDSHIP", "DOCUMENTS", "CONTACT_UPDATE"]
PRIORITIES = ["LOW", "NORMAL", "HIGH", "URGENT"]
CASE_STATUSES = ["OPEN", "IN_PROGRESS", "WAITING_CUSTOMER", "RESOLVED", "CLOSED"]


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def customer_template() -> list[dict]:
    return [{"record_type": "customer", "source_record_id": "demo-customer-001", "source_version": 1,
             "full_name": "Asha Demo", "city": "Pune", "segment": "SALARIED", "monthly_income": 45000,
             "preferred_language": "English", "consent_calls": False, "consent_marketing": False,
             "dnd": False}]


def source_template() -> list[dict]:
    """Four matching fictional source records; stable within the current day."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    due = (today - timedelta(days=7)).date().isoformat()
    return [*customer_template(),
        {"record_type": "loan", "source_record_id": "demo-loan-001", "source_version": 1,
         "customer_ref": "demo-customer-001", "product": "PERSONAL_LOAN", "principal": 200000,
         "outstanding": 160000, "interest_rate": 13, "emi": 8000, "relationship_months": 12,
         "current_dpd": 0, "status": "ACTIVE", "disbursed_on": (today - timedelta(days=365)).date().isoformat()},
        {"record_type": "payment", "source_record_id": "demo-payment-001", "source_version": 1,
         "loan_ref": "demo-loan-001", "due_date": due, "paid_date": due, "amount_due": 8000,
         "amount_paid": 8000, "status": "PAID"},
        {"record_type": "interaction", "source_record_id": "demo-interaction-001", "source_version": 1,
         "customer_ref": "demo-customer-001", "channel": "CHAT", "ts": today.isoformat(),
         "text": "Customer: I would like a helpful officer callback to understand my repayment options."},
    ]


def csv_template() -> str:
    rows = customer_template()
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def parse_import(data: bytes, filename: str) -> list[dict]:
    """Bounded CSV/JSON decoding shared by public preview and staff import UI."""
    if not isinstance(data, bytes) or len(data) > MAX_IMPORT_BYTES:
        raise DemoError("Use a CSV or JSON file smaller than 1 MB.")
    try:
        text = data.decode("utf-8-sig")
        if filename.lower().endswith(".csv"):
            stream = StringIO(text)
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            if not fields or len(fields) != len(set(fields)) or len(fields) > 50:
                raise DemoError("CSV needs unique column names and at most 50 columns.")
            records = []
            for row in reader:
                if len(records) >= MAX_IMPORT_RECORDS:
                    raise DemoError("One import can contain at most 200 records.")
                if None in row or any(value is None for value in row.values()):
                    raise DemoError("Every CSV row must match its header.")
                # CSV values are strings; convert booleans explicitly rather than
                # treating the string 'false' as truthy.
                for key in ("consent_calls", "consent_marketing", "dnd", "identity_review", "document_review", "document_review_attested"):
                    if key in row:
                        raw = row[key].strip().lower()
                        if raw in {"true", "1"}:
                            row[key] = True
                        elif raw in {"false", "0", ""}:
                            row[key] = False
                        else:
                            raise DemoError(f"Column {key} must contain true or false.")
                for key in ("source_version", "relationship_months", "current_dpd"):
                    if key in row:
                        try:
                            row[key] = int(row[key].strip())
                        except ValueError as error:
                            raise DemoError(f"Column {key} must contain a whole number.") from error
                for key in ("monthly_income", "principal", "outstanding", "interest_rate", "emi", "amount_due", "amount_paid"):
                    if key in row:
                        try:
                            row[key] = float(row[key].strip())
                        except ValueError as error:
                            raise DemoError(f"Column {key} must contain a number.") from error
                        if not math.isfinite(row[key]):
                            raise DemoError(f"Column {key} must contain a finite number.")
                records.append(row)
        elif filename.lower().endswith(".json"):
            def object_fields(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise DemoError("JSON record fields must be unique.")
                    result[key] = value
                return result
            def invalid_constant(_value):
                raise DemoError("JSON numbers must be finite.")
            records = json.loads(text, object_pairs_hook=object_fields, parse_constant=invalid_constant)
        else:
            raise DemoError("Choose a CSV or JSON file.")
    except (UnicodeError, ValueError, csv.Error, RecursionError) as error:
        if isinstance(error, DemoError):
            raise
        raise DemoError("The file is not valid UTF-8 CSV or JSON.") from error
    if not isinstance(records, list) or not records or len(records) > MAX_IMPORT_RECORDS:
        raise DemoError("Upload an array containing 1 to 200 records.")
    if any(not isinstance(row, dict) for row in records):
        raise DemoError("Every record must be an object with named fields.")
    return records


def _normal_customer(payload):
    from samvaad.relationship import normalize_customer
    try:
        candidate = dict(payload)
        # NANP's reserved fictional 555-0100 number validates a fictional
        # permission exercise without accepting or storing a visitor's number.
        if candidate.get("consent_calls") and not candidate.get("phone"):
            candidate["phone"] = "+12025550100"
        result = normalize_customer(candidate)
        result["phone"] = result["email"] = ""
        for key in ("identity_review", "document_review"):
            if not isinstance(payload.get(key, False), bool):
                raise DemoError("Review attestations must be true or false.")
            result[key] = payload.get(key, False)
        reference = payload.get("consent_reference", "")
        if not isinstance(reference, str) or len(reference) > 500:
            raise DemoError("Use a fictional permission reference of up to 500 characters.")
        if (result["consent_calls"] or result["consent_marketing"]) and not reference.strip():
            raise DemoError("Record a fictional permission reference before selecting contact permissions.")
        result["consent_reference"] = reference.strip()
        return result
    except ValueError as error:
        raise DemoError(str(error)) from error


def _fictional_contact_check(payload):
    if payload.get("phone") or payload.get("email"):
        raise DemoError("Public rehearsals do not accept phone numbers or email addresses. Remove contact fields.")


class PublicRelationshipSandbox:
    """Small session-owned rehearsal state; no shared writes or portal tokens."""
    def __init__(self, state: dict | None = None, customers: list[dict] | None = None):
        self.state = state if state is not None else {}
        for key, value in {"applications": [], "customers": {}, "cases": [], "preferences": {},
                           "runs": [], "source_records": {}, "entities": {}}.items():
            self.state.setdefault(key, deepcopy(value))
        self.base_customers = {c["customer_id"]: deepcopy(c) for c in (customers or [])}

    def customers(self):
        return list({**self.base_customers, **self.state["customers"]}.values())

    def link_source_customer(self, source, source_record_id, customer_id, note):
        if not self.contains(customer_id):
            raise DemoError("Onboard a relationship in this visit before linking its source ID.")
        if not isinstance(source, str) or not source.strip() or len(source) > 80 or not isinstance(source_record_id, str) or not source_record_id.strip() or len(source_record_id) > 120:
            raise DemoError("Enter a source label and a stable source customer ID.")
        if not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise DemoError("Record a reviewed identity-mapping note of up to 500 characters.")
        key = source.strip() + ":customer:" + source_record_id.strip()
        current = self.state["source_records"].get(key)
        if current and current["entity_id"] != customer_id:
            raise DemoError("A source identity cannot be moved to a different customer.")
        if not current:
            self.state["source_records"][key] = {"source": source.strip(), "record_type": "customer", "source_record_id": source_record_id.strip(),
                "entity_id": customer_id, "version": 0, "digest": "reviewed-mapping", "updated_at": timestamp(), "mapping_note": note.strip()}
        return deepcopy(self.state["source_records"][key])

    def contains(self, customer_id):
        return customer_id in self.state["customers"]

    def customer360(self, customer_id):
        """Build a visit-owned 360 using the same decision rules as the snapshot."""
        from samvaad.engine import CATALOGUE, compute_metrics, decide_customer
        from samvaad.signals import extract_signals
        if not self.contains(customer_id):
            raise DemoError("Select a relationship added in this visit.")
        customer = deepcopy(self.state["customers"][customer_id])
        customer.setdefault("phone", "Not collected in public rehearsal")
        customer.setdefault("email", "Not collected in public rehearsal")
        customer.update(self.state["preferences"].get(customer_id, {}))
        customers_by_source = {(r.get("source"), r["source_record_id"]): r["entity_id"]
            for r in self.state["source_records"].values() if r.get("record_type") == "customer"}
        loans, interactions = [], []
        for key, record in self.state["entities"].items():
            mapping = self.state["source_records"][key]
            ref = record.get("customer_ref")
            cid = customers_by_source.get((mapping["source"], ref), ref)
            if cid != customer_id:
                continue
            payload = {k: v for k, v in record.items() if k not in {"record_type", "source_record_id", "source_version", "customer_ref"}}
            if record["record_type"] == "loan":
                loans.append({**payload, "loan_id": mapping["entity_id"], "customer_id": customer_id})
            elif record["record_type"] == "interaction":
                signals = extract_signals(payload["text"])
                interactions.append({**payload, **signals, "interaction_id": mapping["entity_id"], "customer_id": customer_id})
        loan_ids = {l["loan_id"] for l in loans}
        source_loans = {(r.get("source"), r["source_record_id"]): r["entity_id"]
            for r in self.state["source_records"].values() if r.get("record_type") == "loan"}
        payments = []
        for key, record in self.state["entities"].items():
            if record["record_type"] != "payment":
                continue
            mapping = self.state["source_records"][key]
            lid = source_loans.get((mapping["source"], record["loan_ref"]), record["loan_ref"])
            if lid in loan_ids:
                payload = {k: v for k, v in record.items() if k not in {"record_type", "source_record_id", "source_version", "loan_ref"}}
                payments.append({**payload, "payment_id": mapping["entity_id"], "loan_id": lid})
        interactions.extend(self.case_interactions(customer_id))
        interactions.sort(key=lambda i: i["ts"], reverse=True)
        metrics = compute_metrics(customer, loans, payments, interactions)
        return {"customer": customer, "loans": loans, "payments": payments, "interactions": interactions,
                "metrics": metrics, "decision": decide_customer(customer, metrics, interactions, CATALOGUE),
                "source": "Visit-local relationship rehearsal", "rehearsal": True}

    def portfolio_profiles(self):
        return [self.customer360(cid) for cid in self.state["customers"]]

    def case_interactions(self, customer_id):
        """Turn hardship/complaint requests into dated, attributed visit evidence.

        The customer-selected category is an explicit structured signal, not a
        claim that a model verified hardship. Financial records stay unchanged.
        """
        from samvaad.signals import extract_signals
        interactions = []
        for case in self.state["cases"]:
            if case["customer_id"] != customer_id or case["category"] not in {"HARDSHIP", "COMPLAINT"}:
                continue
            text = "Customer service request: " + case["subject"] + ". " + case["description"]
            signals = extract_signals(text)
            intent = ("financial hardship" if case["category"] == "HARDSHIP" else
                      "complaint about service or rate" if signals["intent"] == "general query" else signals["intent"])
            signals.update(intent=intent,
                provider="Visit service-case category + deterministic text signals", extraction_version="relationship-case-v1")
            signals["entities"]["case_category"] = case["category"]
            interactions.append({**signals, "interaction_id": case["case_id"], "customer_id": customer_id,
                "channel": "PORTAL", "text": text, "ts": case["created_at"],
                "simulated": True, "intent_source": "Fictional customer service-case category"})
        return interactions

    def submit(self, payload):
        if len(self.state["applications"]) >= 50:
            raise DemoError("This visit has reached its 50-application rehearsal limit.")
        _fictional_contact_check(payload)
        customer = _normal_customer(payload)
        application = {"application_id": "APP-" + uuid4().hex[:10], "status": "SUBMITTED",
                       "payload": customer, "created_at": timestamp(), "customer_id": None, "review_note": ""}
        self.state["applications"].append(application)
        return deepcopy(application)

    def review(self, application_id, decision, note):
        application = next((a for a in self.state["applications"] if a["application_id"] == application_id), None)
        if not application:
            raise DemoError("This application belongs to a different visit or no longer exists.")
        if application["status"] != "SUBMITTED":
            raise DemoError("This application has already been reviewed.")
        if decision not in {"APPROVE", "REJECT"} or not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise DemoError("Choose an approval or rejection and enter a review note of up to 500 characters.")
        payload = application["payload"]
        if decision == "APPROVE" and not (payload.get("identity_review") and payload.get("document_review")):
            raise DemoError("Record both identity and document review attestations before approval. They are not an automated KYC check.")
        application.update(status="APPROVED" if decision == "APPROVE" else "REJECTED", review_note=note.strip(), reviewed_at=timestamp())
        if decision == "APPROVE":
            cid = "VCRM-" + uuid4().hex[:10]
            application["customer_id"] = cid
            self.state["customers"][cid] = {"customer_id": cid, **deepcopy(payload), "origin": "Visit onboarding"}
        return deepcopy(application)

    def preview(self, source, records):
        from samvaad.relationship import normalize_sync_record
        if not isinstance(source, str) or not source.strip() or len(source) > 80:
            raise DemoError("Enter a source label of up to 80 characters.")
        if not isinstance(records, list) or not 1 <= len(records) <= MAX_IMPORT_RECORDS:
            raise DemoError("Preview 1 to 200 records at a time.")
        if len(self.state["runs"]) >= 30:
            raise DemoError("This visit has reached its 30-import preview limit.")
        normalized, errors, seen = [], [], set()
        summary = {"new": 0, "updated": 0, "unchanged": 0, "conflicts": 0}
        for index, record in enumerate(records, start=1):
            try:
                _fictional_contact_check(record)
                item = normalize_sync_record(record)
                key = source.strip() + ":" + item["record_type"] + ":" + item["source_record_id"]
                if key in seen:
                    raise DemoError("A source record appears more than once in this file.")
                seen.add(key)
                digest = sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                current = self.state["source_records"].get(key)
                if current and item["source_version"] < current["version"]:
                    raise DemoError("Source version is older than the last imported version.")
                if current and item["source_version"] == current["version"] and digest != current["digest"]:
                    raise DemoError("The source version is unchanged but its content has changed.")
                old_entity = self.state["entities"].get(key)
                if old_entity and any(old_entity.get(ref) != item.get(ref) for ref in ("customer_ref", "loan_ref")):
                    raise DemoError("A committed source record cannot move to a different customer or loan.")
                change = "new" if current is None else ("unchanged" if digest == current["digest"] else "updated")
                summary[change] += 1
                normalized.append({"key": key, "record": item, "digest": digest, "change": change, "row": index})
            except ValueError as error:
                summary["conflicts"] += 1
                errors.append({"row": index, "message": str(error)})
        # Validate references against this source's customer/loan records and
        # the selected fictional snapshot. Never infer matches from names.
        customer_refs = set()
        loan_refs = set()
        for key, current in self.state["source_records"].items():
            if key.startswith(source.strip() + ":customer:"):
                customer_refs.add(current["source_record_id"])
            if key.startswith(source.strip() + ":loan:"):
                loan_refs.add(current["source_record_id"])
        customer_refs.update(i["record"]["source_record_id"] for i in normalized if i["record"]["record_type"] == "customer")
        loan_refs.update(i["record"]["source_record_id"] for i in normalized if i["record"]["record_type"] == "loan")
        for item in normalized:
            record = item["record"]
            ref = record.get("loan_ref") if record["record_type"] == "payment" else record.get("customer_ref")
            allowed = loan_refs if record["record_type"] == "payment" else customer_refs
            if ref is not None and ref not in allowed:
                summary["conflicts"] += 1
                errors.append({"row": item["row"], "message": "The referenced customer or loan does not exist in this source or visit."})
        run = {"run_id": "RUN-" + uuid4().hex[:10], "source": source.strip(), "status": "INVALID" if errors else "VALIDATED",
               "summary": summary, "errors": errors, "items": normalized, "created_at": timestamp()}
        self.state["runs"].append(run)
        return deepcopy(run)

    def commit(self, run_id):
        run = next((r for r in self.state["runs"] if r["run_id"] == run_id), None)
        if not run or run["status"] != "VALIDATED":
            raise DemoError("Only a validated import from this visit can be rehearsed.")
        # Recheck versions if another preview was applied since this one.
        for item in run["items"]:
            current = self.state["source_records"].get(item["key"])
            record = item["record"]
            if current and (record["source_version"] < current["version"] or
                            (record["source_version"] == current["version"] and item["digest"] != current["digest"])):
                raise DemoError("The source changed after preview. Preview the file again.")
        staged = deepcopy(self.state)
        for item in run["items"]:
            record = item["record"]
            current = staged["source_records"].get(item["key"])
            entity_id = current["entity_id"] if current else "VCRM-" + uuid4().hex[:10]
            staged["source_records"][item["key"]] = {"version": record["source_version"], "digest": item["digest"],
                "source": run["source"], "record_type": record["record_type"], "source_record_id": record["source_record_id"],
                "entity_id": entity_id, "updated_at": timestamp()}
            if record["record_type"] == "customer":
                payload = {k: v for k, v in record.items() if k not in {"record_type", "source_record_id", "source_version"}}
                old = staged["customers"].get(entity_id)
                if old:
                    # A synchronization job cannot re-enable a reduced contact
                    # preference, even if an old source still says opted in.
                    payload["consent_calls"] = old.get("consent_calls", False) and payload.get("consent_calls", False)
                    payload["consent_marketing"] = old.get("consent_marketing", False) and payload.get("consent_marketing", False)
                    payload["dnd"] = old.get("dnd", False) or payload.get("dnd", False)
                else:
                    payload["consent_calls"] = payload["consent_marketing"] = False
                staged["customers"][entity_id] = {"customer_id": entity_id, **payload, "origin": run["source"]}
            else:
                staged["entities"][item["key"]] = deepcopy(record)
        target = next(r for r in staged["runs"] if r["run_id"] == run_id)
        target.update(status="COMMITTED", committed_at=timestamp())
        self.state.clear()
        self.state.update(staged)
        return deepcopy(target)

    def case(self, customer_id, subject, description, category="SERVICE", priority="NORMAL"):
        if customer_id not in {c["customer_id"] for c in self.customers()}:
            raise DemoError("Choose a customer from this visit.")
        if len(self.state["cases"]) >= 100:
            raise DemoError("This visit has reached its 100-case rehearsal limit.")
        if category not in CATEGORIES or priority not in PRIORITIES:
            raise DemoError("Choose a supported case category and priority.")
        if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 160 or not isinstance(description, str) or not 1 <= len(description.strip()) <= 2000:
            raise DemoError("Add a subject (up to 160 characters) and a description (up to 2,000 characters).")
        case = {"case_id": "CASE-" + uuid4().hex[:10], "customer_id": customer_id, "subject": subject.strip(),
                "description": description.strip(), "category": category, "priority": priority, "status": "OPEN", "created_at": timestamp()}
        self.state["cases"].append(case)
        return deepcopy(case)

    def update_case(self, case_id, status, note):
        case = next((c for c in self.state["cases"] if c["case_id"] == case_id), None)
        if not case or status not in CASE_STATUSES or not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise DemoError("Choose this visit's case, a valid status and a note of up to 500 characters.")
        case.update(status=status, last_note=note.strip(), updated_at=timestamp())
        return deepcopy(case)

    def opt_out(self, customer_id):
        if customer_id not in {c["customer_id"] for c in self.customers()}:
            raise DemoError("Choose a customer from this visit.")
        self.state["preferences"][customer_id] = {"consent_calls": False, "consent_marketing": False, "dnd": True}
        if customer_id in self.state["customers"]:
            self.state["customers"][customer_id].update(self.state["preferences"][customer_id])
        return deepcopy(self.state["preferences"][customer_id])


def _perform(action, run_action):
    def safe_action():
        try:
            action()
            st.session_state["relationship_flash"] = "Your visit's relationship workspace was updated."
        except DemoError as error:
            st.session_state["relationship_error"] = str(error)
    if run_action:
        run_action("Customer hub", safe_action)
    else:
        safe_action()
    st.rerun()


def _public_onboarding(hub, run_action):
    st.subheader("Add a fictional customer")
    st.caption("Create an application, record review attestations, then approve it. A relationship record does not approve a loan.")
    with st.form("relationship_onboarding_form"):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Fictional customer name", value="Asha Demo", max_chars=120)
            city = st.text_input("City", value="Pune", max_chars=100)
            segment = st.selectbox("Customer segment", SEGMENTS)
        with right:
            income = st.number_input("Monthly income (₹)", min_value=0.0, value=45000.0, step=1000.0)
            language = st.selectbox("Preferred language", LANGUAGES)
            st.caption("Contact details are excluded from the anonymous website.")
        calls = st.checkbox("Permission recorded for calls", value=False)
        marketing = st.checkbox("Permission recorded for marketing", value=False)
        dnd = st.checkbox("Do not contact", value=False)
        reference = st.text_input("Fictional permission reference", max_chars=500, placeholder="Required when any contact permission is selected")
        identity = st.checkbox("Identity review attested by an officer", value=False)
        documents = st.checkbox("Document review attested by an officer", value=False)
        st.caption("These checkboxes record a fictional review. They do not perform identity verification or KYC.")
        submitted = st.form_submit_button("Submit fictional application", type="primary")
    if submitted:
        payload = dict(full_name=name, city=city, segment=segment, monthly_income=income, preferred_language=language,
                       consent_calls=calls, consent_marketing=marketing, dnd=dnd, consent_reference=reference,
                       identity_review=identity, document_review=documents)
        _perform(lambda: hub.submit(payload), run_action)
    pending = [a for a in hub.state["applications"] if a["status"] == "SUBMITTED"]
    st.markdown("**Application review**")
    if pending:
        with st.form("relationship_review_form"):
            selected = st.selectbox("Application awaiting review", pending, format_func=lambda a: a["payload"]["full_name"] + " · " + a["application_id"])
            decision = st.radio("Fictional reviewer decision", ["APPROVE", "REJECT"], horizontal=True)
            note = st.text_input("Review note", value="Fictional onboarding reviewed", max_chars=500)
            reviewed = st.form_submit_button("Save fictional review")
        if reviewed:
            _perform(lambda: hub.review(selected["application_id"], decision, note), run_action)
    else:
        st.info("Submit an application to start its review. Both review attestations are required for approval.")
    if hub.state["applications"]:
        st.dataframe([{ "Customer": a["payload"]["full_name"], "Status": a["status"], "Customer ID": a.get("customer_id") or "Pending",
                        "Application": a["application_id"]} for a in hub.state["applications"]], hide_index=True, width="stretch")


def _public_sync(hub, run_action):
    st.subheader("Preview and reconcile source data")
    st.caption("CSV/JSON imports use source IDs and versions. Invalid records block the whole import; names alone never merge customers.")
    with st.expander("Link reviewed onboarding to a source customer ID"):
        st.caption("Connect a relationship you added in this visit to its fictional source-system identity before importing loan records.")
        local = list(hub.state["customers"].values())
        if local:
            with st.form("relationship_mapping_form"):
                customer = st.selectbox("Reviewed relationship to link", local, format_func=lambda c: c["full_name"] + " · " + c["customer_id"])
                mapping_source = st.text_input("Fictional source system", value="Fictional lending CRM", max_chars=80)
                mapping_id = st.text_input("Source customer reference", value="demo-customer-001", max_chars=120)
                mapping_note = st.text_input("Fictional identity mapping note", value="Officer matched the fictional application to this source record", max_chars=500)
                mapped = st.form_submit_button("Link fictional source identity")
            if mapped:
                _perform(lambda: hub.link_source_customer(mapping_source, mapping_id, customer["customer_id"], mapping_note), run_action)
        else:
            st.info("Approve an onboarding application first, then link its source ID here.")
    left, right = st.columns(2)
    left.download_button("Download customer CSV template", csv_template(), "samvaad-customers-template.csv", "text/csv", key="relationship_csv_template")
    right.download_button("Download full relationship JSON example", json.dumps(source_template(), indent=2), "samvaad-fictional-relationship.json", "application/json", key="relationship_json_template")
    st.caption("CSV covers customer records. The fictional JSON example joins one customer, loan, repayment and conversation with matching source references. Its figures are demonstration data.")
    source = st.text_input("Source label", value="Fictional lending CRM", max_chars=80, key="relationship_source")
    uploaded = st.file_uploader("Upload fictional CSV or JSON · 1 MB / 200 records", type=["csv", "json"], max_upload_size=1, key="relationship_import")
    if st.button("Preview sample import" if uploaded is None else "Validate uploaded import", type="primary", key="relationship_preview"):
        def preview():
            records = parse_import(uploaded.getvalue(), uploaded.name) if uploaded else source_template()
            result = hub.preview(source, records)
            st.session_state["relationship_selected_run"] = result["run_id"]
        _perform(preview, run_action)
    selected = st.session_state.get("relationship_selected_run")
    run = next((r for r in hub.state["runs"] if r["run_id"] == selected), None)
    if run:
        cols = st.columns(4)
        for col, key in zip(cols, ("new", "updated", "unchanged", "conflicts")):
            col.metric(key.title(), run["summary"].get(key, 0))
        st.write("Import status: **" + run["status"] + "**")
        if run["errors"]:
            st.error("Correct every rejected row, then preview again. Nothing has been applied.")
            st.dataframe(run["errors"], hide_index=True, width="stretch")
        else:
            st.dataframe([{"Type": i["record"]["record_type"], "Source ID": i["record"]["source_record_id"],
                           "Version": i["record"]["source_version"], "Change": i["change"]} for i in run["items"]], hide_index=True, width="stretch")
        apply = st.checkbox("Apply these fictional records to this visit only", key="relationship_commit_permission")
        if st.button("Apply rehearsal import", disabled=run["status"] != "VALIDATED" or not apply, key="relationship_commit"):
            _perform(lambda: hub.commit(run["run_id"]), run_action)
    if hub.state["runs"]:
        st.markdown("**Source run history · this visit**")
        st.dataframe([{k: r.get(k) for k in ("source", "status", "run_id", "created_at")} for r in hub.state["runs"]], hide_index=True, width="stretch")
    if hub.state["source_records"]:
        st.markdown("**Source identity registry · this visit**")
        st.dataframe([{"Source": r["source"], "Record type": r["record_type"], "Source ID": r["source_record_id"], "Version": r["version"],
                       "Relationship ID": r["entity_id"]} for r in hub.state["source_records"].values()], hide_index=True, width="stretch")
        st.caption("Version zero records reserve a reviewed identity mapping; version one and later are applied source data. Imports do not grant contact permission.")


def _public_cases(hub, run_action, selected_cid):
    st.subheader("Manage relationship requests")
    customers = hub.customers()
    if not customers:
        st.info("Approve an onboarding application or apply a fictional import first.")
        return
    ids = [c["customer_id"] for c in customers]
    index = ids.index(selected_cid) if selected_cid in ids else 0
    cid = st.selectbox("Relationship customer", ids, index=index, format_func=lambda value: next(c["full_name"] for c in customers if c["customer_id"] == value), key="relationship_case_customer")
    with st.form("relationship_case_form"):
        subject = st.text_input("Request subject", value="Officer callback requested", max_chars=160)
        description = st.text_area("Fictional request details", value="Please arrange a suitable time to discuss support options.", max_chars=2000)
        left, right = st.columns(2)
        category = left.selectbox("Case category", CATEGORIES)
        priority = right.selectbox("Case priority", PRIORITIES, index=1)
        submitted = st.form_submit_button("Create relationship case", type="primary")
    if submitted:
        _perform(lambda: hub.case(cid, subject, description, category, priority), run_action)
    cases = [c for c in hub.state["cases"] if c["customer_id"] == cid]
    if cases:
        st.dataframe([{k: c.get(k) for k in ("subject", "category", "priority", "status", "case_id")} for c in cases], hide_index=True, width="stretch")
        with st.form("relationship_case_update_form"):
            case = st.selectbox("Case to update", cases, format_func=lambda c: c["subject"] + " · " + c["status"])
            status = st.selectbox("Next case status", CASE_STATUSES)
            note = st.text_input("Progress note", max_chars=500)
            update = st.form_submit_button("Save case progress")
        if update:
            _perform(lambda: hub.update_case(case["case_id"], status, note), run_action)
    else:
        st.caption("No relationship requests for this customer in your visit yet.")


def _public_portal(hub, run_action, selected_cid):
    st.subheader("Borrower self-service preview")
    st.caption("A customer-scoped operational portal is available through private invitations. This public preview issues no invitation or access token.")
    customers = hub.customers()
    if not customers:
        st.info("Add a fictional relationship to preview its self-service view.")
        return
    ids = [c["customer_id"] for c in customers]
    index = ids.index(selected_cid) if selected_cid in ids else 0
    cid = st.selectbox("Preview as fictional customer", ids, index=index, format_func=lambda value: next(c["full_name"] for c in customers if c["customer_id"] == value), key="relationship_portal_customer")
    customer = next(c for c in customers if c["customer_id"] == cid)
    preferences = hub.state["preferences"].get(cid, customer)
    st.write("**" + customer["full_name"] + "** · " + customer.get("city", "") + " · " + customer.get("preferred_language", "English"))
    a, b, c = st.columns(3)
    a.metric("Service calls", "Allowed" if preferences.get("consent_calls") and not preferences.get("dnd") else "On hold")
    b.metric("Marketing", "Allowed" if preferences.get("consent_marketing") and not preferences.get("dnd") else "On hold")
    c.metric("Open requests", sum(case["status"] not in {"RESOLVED", "CLOSED"} for case in hub.state["cases"] if case["customer_id"] == cid))
    if st.button("Rehearse withdrawing all contact permission", key="relationship_optout"):
        _perform(lambda: hub.opt_out(cid), run_action)
    with st.form("relationship_portal_request_form"):
        subject = st.text_input("Self-service request", value="Update my communication preference", max_chars=160)
        detail = st.text_area("Fictional message to the relationship team", value="Please confirm my request and show its progress here.", max_chars=2000)
        submitted = st.form_submit_button("Submit self-service request")
    if submitted:
        _perform(lambda: hub.case(cid, subject, detail, "CONTACT_UPDATE"), run_action)
    requests = [case for case in hub.state["cases"] if case["customer_id"] == cid]
    if requests:
        st.dataframe([{k: case.get(k) for k in ("subject", "status", "created_at")} for case in requests], hide_index=True, width="stretch")
    st.caption("Requests and permission withdrawals update Customer 360 and contact holds throughout this visit. Shared Snowflake records remain separate, and this preview cannot authorise a telephone call.")


def render_relationship_hub(reader, sandbox=None, run_action=None, selected_cid=None):
    """Render customer lifecycle exercises; safe for anonymous website visitors."""
    # The existing review sandbox argument is intentionally unused. Relationship
    # exercises cannot create executable review approvals or carrier permissions.
    del sandbox
    state = st.session_state.setdefault("public_relationship_state", {})
    hub = PublicRelationshipSandbox(state, reader.customers())
    st.subheader("Customer relationship hub")
    st.caption("Bring data in, review a new relationship, resolve requests, and give the customer a clear self-service journey.")
    st.info("Fictional rehearsal · changes stay in your browser visit. Do not enter real personal data. Snowflake remains read-only here.")
    left, middle, right = st.columns(3)
    left.metric("Shared snapshot customers", len(hub.base_customers))
    middle.metric("Added in this visit", len(hub.state["customers"]))
    right.metric("Relationship requests", len(hub.state["cases"]))
    st.markdown("**Source data → Validate and reconcile → Officer review → Customer 360 → Service and self-service**")
    with st.expander("How customer data reaches this website"):
        st.write("The shared portfolio contains fictional seeded customers, loans, repayments and interactions. With Snowflake available, the website refreshes its shared read-only snapshot hourly; browsing does not query Snowflake per customer. Its clearly labelled bundled fallback remains available if the cloud snapshot cannot be loaded.")
        st.write("The operational portal adds persistent onboarding, source-versioned CSV/JSON imports, service cases and scoped borrower invitations. Its authenticated API deployment and scheduled Snowflake publisher are separate from this anonymous rehearsal.")
        st.caption("The rehearsal import supports customer, loan, payment and interaction records. Contact fields are excluded from public uploads.")
    flash = st.session_state.pop("relationship_flash", None)
    error = st.session_state.pop("relationship_error", None)
    if flash:
        st.success(flash)
    if error:
        st.error(error)
    mode = st.radio("Customer hub workspace", ["Onboarding", "Data sync", "Relationship cases", "Customer portal"], horizontal=True, key="relationship_workspace")
    if mode == "Onboarding":
        _public_onboarding(hub, run_action)
    elif mode == "Data sync":
        _public_sync(hub, run_action)
    elif mode == "Relationship cases":
        _public_cases(hub, run_action, selected_cid)
    else:
        _public_portal(hub, run_action, selected_cid)
