"""Keep relationship rehearsals visible across workspaces within one visit."""
from copy import deepcopy
from datetime import datetime, timezone
import re

from public_app.repository import DemoError, PublicReader
from samvaad.engine import CATALOGUE, compute_metrics, decide_customer


class VisitRelationshipReader(PublicReader):
    """Memory-only adapter. Never place visit data in a shared resource cache."""

    def __init__(self, base, sandbox):
        super().__init__(None)
        self.base, self.sandbox = base, sandbox
        self.reference = getattr(base, "reference", datetime.now(timezone.utc).isoformat())

    @property
    def is_live(self):
        return self.base.is_live

    def source_status(self):
        return self.base.source_status()

    def rows(self, sql, params=None):
        raise DemoError("Relationship rehearsals cannot issue database queries.")

    def customers(self):
        result = {row["customer_id"]: deepcopy(row) for row in self.base.customers()}
        for row in self.sandbox.customers():
            result[row["customer_id"]] = deepcopy(row)
        for customer_id, preferences in self.sandbox.state.get("preferences", {}).items():
            if customer_id in result:
                result[customer_id].update(deepcopy(preferences))
        return list(result.values())

    def customer360(self, customer_id):
        view = deepcopy(self.sandbox.customer360(customer_id) if self.sandbox.contains(customer_id)
                        else self.base.customer360(customer_id))
        case_evidence = (self.sandbox.case_interactions(customer_id)
                         if not self.sandbox.contains(customer_id) else [])
        if case_evidence:
            view["interactions"].extend(deepcopy(case_evidence))
            view["interactions"].sort(key=lambda row: row["ts"], reverse=True)
        preferences = self.sandbox.state.get("preferences", {}).get(customer_id)
        if preferences:
            view["customer"].update(deepcopy(preferences))
        if preferences or case_evidence:
            reference = datetime.now(timezone.utc)
            if not case_evidence and not view.get("rehearsal") and not self.is_live:
                reference = datetime.fromisoformat(self.reference.replace("Z", "+00:00"))
            view["metrics"] = compute_metrics(view["customer"], view["loans"], view["payments"], view["interactions"], reference)
            view["decision"] = decide_customer(view["customer"], view["metrics"], view["interactions"], CATALOGUE)
            view.update(rehearsal=True, source="Visit-local relationship rehearsal")
        return deepcopy(view)

    def portfolio_profiles(self):
        return [self.customer360(row["customer_id"]) for row in self.customers()]

    def answer(self, customer_id, question, *, cortex=False):
        if isinstance(question, str):
            for customer in self.customers():
                other = customer["customer_id"]
                if other != customer_id and re.search(r"\b" + re.escape(other) + r"\b", question, re.IGNORECASE):
                    raise DemoError("That question refers to another customer. Change the selected profile first.")
        answer = super().answer(customer_id, question, cortex=cortex)
        if answer["provider"] != "Policy boundary":
            answer["provider"] = ("Visit-local relationship rehearsal + deterministic evidence summary"
                if self.customer360(customer_id).get("rehearsal")
                else "Protected Snowflake snapshot + deterministic evidence summary" if self.is_live
                else "Bundled synthetic snapshot + deterministic evidence summary")
        return answer
