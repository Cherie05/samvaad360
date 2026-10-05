"""A bounded borrower/lender conversation held inside one public website visit.

This module never dials, writes financial data, or impersonates a staff member.
It consumes the same evidence-backed decision and approved simulation review as
the public dashboard. Browser audio is a separate, optional presentation layer.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone

from cloud.demo_app.demo_repository import DemoError, decision_hash
from samvaad.signals import extract_signals

MAX_SESSIONS = 8
MAX_ATTEMPTS_PER_CUSTOMER = 3
MAX_REPLIES = 12
MAX_REPLY_CHARACTERS = 1000
SUPPORTED_ACTIONS = {
    "HARDSHIP_RESTRUCTURE_CALL", "GENTLE_REMINDER_CALL",
    "RETENTION_RATE_MATCH_CALL", "TOPUP_PREAPPROVAL_CALL",
}

_OPT_OUT = re.compile(
    r"\bstop (?:calling|contact(?:ing)?|calls)\b|\b(?:do not|don't|dont|never) "
    r"(?:call|contact)\b|\bunsubscribe\b|\bopt[ -]?out\b|\bremove my number\b|"
    r"\bno more calls\b|\brevoke (?:my )?consent\b"
)
_NEGATIVE = re.compile(
    r"\b(?:no|not|never|decline|refuse|uninterested|disagree|reject|busy|later)\b|"
    r"\b(?:don't|dont|cannot|can't|cant|won't|wont|wouldn't|wouldnt)\b"
)
_CONDITIONAL = re.compile(
    r"\b(?:if|unless|only|but|provided|providing|assuming|suppose|hypothetical|"
    r"instead|negotiate|bypass|override|increase|reduce|change|different|whatever)\b|"
    r"\bdepend(?:s|ing)?\b|\bignore .*?(?:rules|approval)\b"
)
_DECLINE = re.compile(
    r"^no\b|\b(?:decline|refuse|uninterested|reject)\b|\bnot interested\b|"
    r"\b(?:not|don't|dont|do not|cannot|can't|cant|won't|wont|will not|never) "
    r"(?:\w+ ){0,2}(?:accept|agree|proceed|want|interested|go ahead)\b"
)
_HUMAN = re.compile(
    r"\b(?:human|officer|manager|agent|callback|real person)\b|"
    r"\bcall (?:me )?back\b|\bcall (?:me )?later\b"
)
_PAID = re.compile(r"\balready paid\b|\bpayment (?:is )?done\b|\bi have paid\b")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normal(text):
    return re.sub(r"\s+", " ", text.lower().replace("\u2019", "'")).strip()


def _positive(text, stage):
    """Explicit assent, with negation/conditions/questions handled first."""
    if _NEGATIVE.search(text) or _CONDITIONAL.search(text) or "?" in text:
        return False
    if stage == "AWAIT_PERMISSION":
        pattern = r"^(?:yes\b|okay\b|ok\b|go ahead\b|please continue\b|i (?:agree|consent)\b)"
    elif stage == "AWAIT_IDENTITY":
        pattern = r"^(?:yes\b|i am (?:the )?account holder\b|this is (?:me|the account holder)\b|speaking\b)"
    else:
        if re.search(r"\b(?:what|why|how|when|where|explain|details|mean|unsure|maybe)\b|\d", text):
            return False
        pattern = (r"^(?:yes\b|i (?:am interested|accept|agree)\b|interested\b|"
                   r"accept\b|go ahead\b|please proceed\b)")
    return bool(re.search(pattern, text))


def _hardship(text):
    return extract_signals("Customer: " + text)["intent"] == "financial hardship"


class CallSandbox:
    """Public call simulation; ``state`` and ``reviews`` belong to one visit.

    Pass a dict from Streamlit session state, the public reader, and the list
    used by ReviewSandbox. All returned records are copies. Permission and a
    verbal synthetic identity gate precede account terms; neither gate is a
    production authentication mechanism.
    """

    def __init__(self, state, reader, reviews=None):
        if not isinstance(state, dict):
            raise DemoError("The call studio needs a visit-local state dictionary.")
        self.state, self.reader, self.reviews = state, reader, reviews if reviews is not None else []
        self.state.setdefault("sessions", [])
        self.state.setdefault("suppressed_contacts", [])
        self.state.setdefault("hardship_holds", [])
        self.state.setdefault("attempts", {})

    def _record(self, session_id):
        record = next((r for r in self.state["sessions"] if r["session_id"] == session_id), None)
        if record is None:
            raise DemoError("This conversation is unavailable in your current visit.")
        return record

    def get(self, session_id):
        return copy.deepcopy(self._record(session_id))

    def sessions(self, customer_id=None):
        records = [s for s in reversed(self.state["sessions"])
                   if customer_id is None or s["customer_id"] == customer_id]
        return copy.deepcopy(records)

    def current(self, customer_id=None):
        records = self.sessions(customer_id)
        return next((s for s in records if s["state"] != "ENDED"), records[0] if records else None)

    def _view(self, customer_id):
        view = self.reader.customer360(customer_id)
        customer, decision = view["customer"], view["decision"]
        if customer_id in self.state["suppressed_contacts"]:
            raise DemoError("This visit's opt-out blocks further contact with this customer.")
        if customer_id in self.state["hardship_holds"]:
            raise DemoError("New hardship evidence places contact on hold for this visit. "
                            "An officer must review the changed situation before another conversation.")
        if not customer.get("consent_calls") or customer.get("dnd"):
            raise DemoError("Calls are suppressed by consent or Do Not Disturb preferences.")
        if decision["action_code"] not in SUPPORTED_ACTIONS:
            raise DemoError("No contact action is eligible under the current policy.")
        return view

    def eligible_review(self, customer_id):
        view = self._view(customer_id)
        fingerprint = decision_hash(view["decision"])
        review = next((r for r in reversed(self.reviews)
                       if r.get("customer_id") == customer_id
                       and r.get("status") == "APPROVED_IN_SIMULATION"
                       and r.get("fingerprint") == fingerprint
                       and decision_hash(r.get("decision", {})) == fingerprint), None)
        return copy.deepcopy(review) if review else None

    def start(self, customer_id, review_id=None):
        view = self._view(customer_id)
        review = self.eligible_review(customer_id)
        if review_id is not None:
            review = next((r for r in self.reviews
                           if r.get("id") == review_id and r.get("customer_id") == customer_id
                           and r.get("status") == "APPROVED_IN_SIMULATION"
                           and r.get("fingerprint") == decision_hash(view["decision"])
                           and decision_hash(r.get("decision", {})) == decision_hash(view["decision"])), None)
        if review is None:
            raise DemoError("Approve the current proposal in Review simulation before starting a demo call.")
        active = next((s for s in self.state["sessions"]
                       if s["customer_id"] == customer_id and s["state"] != "ENDED"), None)
        if active:
            if active["fingerprint"] != decision_hash(view["decision"]):
                self._finish(active, "HUMAN_HANDOFF", "The recommendation changed. An officer must review a fresh proposal.")
                raise DemoError("The recommendation changed. Review a fresh proposal before another demo call.")
            return copy.deepcopy(active)
        if len(self.state["sessions"]) >= MAX_SESSIONS:
            raise DemoError(f"This visit has reached its {MAX_SESSIONS}-conversation limit.")
        attempts = self.state["attempts"].get(customer_id, 0)
        if attempts >= MAX_ATTEMPTS_PER_CUSTOMER:
            raise DemoError("This visit's three-attempt limit has been reached for this customer.")
        record = {
            "session_id": uuid.uuid4().hex, "customer_id": customer_id, "review_id": review["id"],
            "decision": copy.deepcopy(view["decision"]), "fingerprint": decision_hash(view["decision"]),
            "state": "AWAIT_PERMISSION", "permission_granted": False, "identity_confirmed": False,
            "reply_count": 0, "turns": [], "outcome": None, "started_at": _now(), "ended_at": None,
            "simulation_only": True, "real_call_placed": False, "financial_execution": False,
            "simulated_invitation": None, "events": ["SIMULATION_REVIEW_CHECKED"],
            "new_evidence": None, "decision_before": copy.deepcopy(view["decision"]),
            "decision_after": None, "policy_change": None,
        }
        self.state["sessions"].append(record)
        self.state["attempts"][customer_id] = attempts + 1
        self._say(record, "lender", "Hello. I am Samvaad, an automated assistant for fictional DemoLend. "
                  "This is a browser conversation demo, not a phone call. May we continue and keep a transcript "
                  "for this visit? You can decline or ask us to stop at any time.")
        return copy.deepcopy(record)

    @staticmethod
    def _say(record, role, text):
        record["turns"].append({"seq": len(record["turns"]) + 1, "role": role, "text": text, "ts": _now()})

    def _finish(self, record, outcome, closing):
        self._say(record, "lender", closing)
        record.update(state="ENDED", outcome=outcome, ended_at=_now())
        record["events"].append(outcome)
        return copy.deepcopy(record)

    @staticmethod
    def _adapt(record, view, scenario, text):
        from public_app.insights import simulate_interaction

        change = simulate_interaction(view, scenario, text=text)
        record.update(new_evidence=copy.deepcopy(change["added_evidence"]),
                      decision_before=copy.deepcopy(change["before"]),
                      decision_after=copy.deepcopy(change["after"]), policy_change=change)
        record["events"].append("BORROWER_EVIDENCE_REEVALUATED")

    @staticmethod
    def _proposal(record):
        decision, offer = record["decision"], record["decision"]["offer"]
        if decision["action_code"] == "RETENTION_RATE_MATCH_CALL":
            return (f"The proposal approved in this simulation is a reduction of {offer['rate_cut_bps']} basis points, "
                    f"from {offer['current_rate']:g}% to an illustrative {offer['proposed_rate']:g}%. "
                    "This does not change your loan or guarantee a match with another lender. "
                    "Would you like to record interest in these terms, decline, or speak with an officer?")
        if decision["action_code"] == "TOPUP_PREAPPROVAL_CALL":
            return (f"The simulation-approved conditional invitation is for up to {offer['amount']:,.0f} rupees, "
                    f"at an indicative {offer['indicative_rate']:g}% for {offer['tenure_months']} months, "
                    f"with a {offer['processing_fee_pct']:g}% processing fee. Document and eligibility checks remain. "
                    "This is a fictional invitation, not a guaranteed loan or disbursement. "
                    "Would you like to record interest, decline, or speak with an officer?")
        if decision["action_code"] == "HARDSHIP_RESTRUCTURE_CALL":
            return ("Your earlier conversation suggests you may need repayment support. I can record an officer "
                    "handoff to discuss options. No payment break, restructuring, or rate change is promised. "
                    "Would you like that officer handoff?")
        return ("The reviewed proposal is a respectful reminder about a pending payment. If you have already "
                "paid, need support, or prefer an officer, I can record that for review without changing payment records.")

    def reply(self, session_id, text):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_REPLY_CHARACTERS:
            raise DemoError(f"Enter a fictional borrower reply of 1–{MAX_REPLY_CHARACTERS} characters.")
        record = self._record(session_id)
        if record["state"] == "ENDED":
            raise DemoError("This conversation has ended. Start a new simulation if contact remains eligible.")
        text = text.strip()
        low = _normal(text)
        record["reply_count"] += 1
        if _OPT_OUT.search(low):
            if record["permission_granted"]:
                self._say(record, "borrower", text)
            if record["customer_id"] not in self.state["suppressed_contacts"]:
                self.state["suppressed_contacts"].append(record["customer_id"])
            current = self.reader.customer360(record["customer_id"])
            if record["permission_granted"]:
                self._adapt(record, current, "opt_out", text)
            else:
                # Honor opt-out before transcript permission without retaining
                # the customer's unconsented utterance as quoted evidence.
                self._adapt(record, current, "opt_out", "Customer withdraws contact consent")
                record["new_evidence"]["evidence_text"] = "Consent withdrawal recorded; unconsented speech omitted."
                record["new_evidence"]["text"] = record["new_evidence"]["evidence_text"]
                record["policy_change"]["added_evidence"] = copy.deepcopy(record["new_evidence"])
            return self._finish(record, "OPT_OUT_FOR_VISIT", "Your opt-out is recorded for this visit. "
                                "Further demo contact is blocked. No Snowflake customer preference was changed.")
        current = self.reader.customer360(record["customer_id"])
        customer = current["customer"]
        if not customer.get("consent_calls") or customer.get("dnd"):
            return self._finish(record, "CONTACT_SUPPRESSED", "Contact permission changed. This conversation "
                                "has stopped without changing a loan or recording a new borrower preference.")
        if decision_hash(current["decision"]) != record["fingerprint"]:
            return self._finish(record, "HUMAN_HANDOFF", "The recommendation changed. A fresh review is "
                                "needed; I cannot continue with the earlier terms.")
        if record["permission_granted"]:
            self._say(record, "borrower", text)
        if _hardship(text):
            record["events"].append("HARDSHIP_OVERRIDE")
            self.state["hardship_holds"].append(record["customer_id"])
            if record["permission_granted"]:
                self._adapt(record, current, "job_loss", text)
            else:
                # Keep the protective hold while omitting speech for which
                # transcript permission was not granted.
                self._adapt(record, current, "job_loss", text)
                record["new_evidence"]["evidence_text"] = "Hardship concern recorded; unconsented speech omitted."
                record["new_evidence"]["text"] = record["new_evidence"]["evidence_text"]
                record["policy_change"]["added_evidence"] = copy.deepcopy(record["new_evidence"])
                record["events"].append("UNCONSENTED_HARDSHIP_HOLD")
            return self._finish(record, "HUMAN_HANDOFF", "You mentioned repayment hardship. The demo "
                                "has switched to a supportive officer handoff. I will not create a top-up "
                                "or rate invitation, and no relief terms are promised.")
        stage = record["state"]
        if _HUMAN.search(low):
            return self._finish(record, "HUMAN_HANDOFF", "An officer handoff is recorded in this demo. "
                                "No real callback has been scheduled or placed.")
        if stage in {"AWAIT_PERMISSION", "AWAIT_IDENTITY"}:
            if _NEGATIVE.search(low) or re.search(r"\bwrong (?:person|number)\b", low):
                outcome = "PERMISSION_DECLINED" if stage == "AWAIT_PERMISSION" else "IDENTITY_NOT_CONFIRMED"
                return self._finish(record, outcome, "We will stop here without discussing account terms. "
                                    "No real call or financial change was made.")
            if _positive(low, stage):
                if stage == "AWAIT_PERMISSION":
                    record.update(permission_granted=True, state="AWAIT_IDENTITY")
                    record["events"].append("TRANSCRIPT_PERMISSION_GRANTED")
                    self._say(record, "borrower", text)
                    self._say(record, "lender", "Thank you. For this fictional test, please confirm you are "
                              "the account holder. This verbal demo gate is not production identity verification.")
                else:
                    record.update(identity_confirmed=True, state="ACTIVE")
                    record["events"].append("SYNTHETIC_IDENTITY_CONFIRMED")
                    self._say(record, "lender", self._proposal(record))
            else:
                self._say(record, "lender", "Please explicitly say yes to continue and keep a transcript, "
                          "or no to stop." if stage == "AWAIT_PERMISSION" else
                          "Please confirm you are the fictional account holder, or say no to stop. "
                          "Account terms stay private until that confirmation.")
        elif _PAID.search(low):
            return self._finish(record, "PAYMENT_REVIEW_SIMULATION", "Your reported payment is recorded "
                                "for review in this demo. The verified payment records have not changed.")
        elif _DECLINE.search(low):
            return self._finish(record, "DECLINED_SIMULATION", "Your decline is recorded for this visit. "
                                "No invitation or loan change was created.")
        elif _CONDITIONAL.search(low) or re.search(r"\d", low):
            record["events"].append("TERMS_CHANGE_BLOCKED")
            self._say(record, "lender", "I cannot negotiate or authorize different terms, and conditional "
                      "interest is not acceptance. I can record interest in the exact reviewed proposal "
                      "or an officer handoff.")
        elif _positive(low, stage):
            if record["decision"]["action_code"] in {"RETENTION_RATE_MATCH_CALL", "TOPUP_PREAPPROVAL_CALL"}:
                record["simulated_invitation"] = {
                    "invitation_id": "DEMO-" + record["session_id"][:12], "mode": "SIMULATION_ONLY",
                    "customer_id": record["customer_id"], "action_code": record["decision"]["action_code"],
                    "offer": copy.deepcopy(record["decision"]["offer"]), "review_id": record["review_id"],
                    "delivery_sent": False, "financial_execution": False,
                }
                return self._finish(record, "INTEREST_RECORDED_SIMULATION", "Your interest in the reviewed "
                                    "terms is recorded. A fictional invitation is available in this visit's "
                                    "call result. No link was sent, loan issued, or rate changed.")
            return self._finish(record, "HUMAN_HANDOFF", "Your officer handoff request is recorded "
                                "in this demo. No real callback was scheduled and no financial terms changed.")
        else:
            self._say(record, "lender", "I can record interest in the exact reviewed proposal, a decline, "
                      "or an officer handoff. You can also say stop calling. I cannot approve new terms.")
        if record["reply_count"] >= MAX_REPLIES:
            return self._finish(record, "HUMAN_HANDOFF", "This demo's conversation limit has been reached. "
                                "An officer handoff is recorded instead of guessing your preference.")
        return copy.deepcopy(record)

    def end(self, session_id):
        record = self._record(session_id)
        if record["state"] == "ENDED":
            return copy.deepcopy(record)
        return self._finish(record, "ENDED_BY_VISITOR", "The visitor ended this browser demo. "
                            "No real call was placed and no financial change was made.")

    def export(self, session_id=None):
        records = [self.get(session_id)] if session_id else self.sessions()
        return json.dumps({"mode": "public-session-call-simulation", "real_call_placed": False,
                           "financial_execution": False, "sessions": records}, ensure_ascii=False, indent=2)
