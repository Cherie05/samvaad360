"""Authenticated relationship operations and narrowly scoped borrower links."""
from __future__ import annotations

import html
import json
import re
import secrets
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from samvaad.relationship import RelationshipService


def _safe(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _key(request):
    value = request.headers.get("Idempotency-Key", "")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}", value):
        raise HTTPException(422, "Supply an Idempotency-Key with 8–100 letters, digits or . _ : -.")
    return value


async def _read(request, maximum):
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            raise HTTPException(413, "This request exceeds the permitted size.")
        content.extend(chunk)
    return bytes(content)


async def _object(request, maximum=32768):
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise HTTPException(415, "Use application/json.")
    def unique_fields(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("Duplicate JSON field")
            result[name] = value
        return result

    try:
        value = json.loads((await _read(request, maximum)).decode("utf-8"),
                           object_pairs_hook=unique_fields,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, "Supply valid finite JSON.") from None
    if not isinstance(value, dict):
        raise HTTPException(422, "Supply a JSON object.")
    return value


def _fields(value, allowed, required=()):
    if set(value) - set(allowed) or set(required) - set(value):
        raise HTTPException(422, "Required fields are missing or unsupported fields were supplied.")


def _portal_page(view, token, message=""):
    """Escaped, capability-scoped forms; never expose the staff customer API."""
    purpose = view.get("purpose", "CUSTOMER")
    customer = view.get("customer", {})
    if not isinstance(customer, dict):
        customer = {}
    cid = view.get("customer_id") or customer.get("customer_id") or ""
    name = customer.get("full_name") or view.get("full_name") or view.get("given_name") or "Your relationship"
    title = "Start your customer application" if purpose == "ONBOARDING" else "Your customer relationship"
    event_id = "portal:" + secrets.token_hex(16)
    hidden = f'<input type="hidden" name="event_id" value="{event_id}">'
    action = f'/portal/{_safe(token)}/submit'
    flash = f'<div class="notice" role="status">{_safe(message)}</div>' if message else ""
    status = view.get("onboarding", {}) or {}
    status_text = (status.get("status") if isinstance(status, dict) else None) or view.get("application_status")
    if status_text == "NOT_SUBMITTED":
        status_text = None
    summary = f'<p class="muted">Application status: {_safe(status_text)}</p>' if status_text else ""
    if purpose == "ONBOARDING" and not status_text:
        forms = f'''<section><h2>Application details</h2>
        <p>Submit your information for staff review. An application does not create a loan or verify your identity.</p>
        <form method="post" action="{action}">{hidden}<input type="hidden" name="request_type" value="APPLY">
        <label>Full name<input name="full_name" required maxlength="120" autocomplete="name"></label>
        <div class="grid"><label>City<input name="city" maxlength="80"></label>
        <label>Monthly income (INR)<input name="monthly_income" type="number" min="0" max="100000000" step="0.01" value="0" required></label></div>
        <div class="grid"><label>Phone (E.164, optional)<input name="phone" maxlength="16" autocomplete="tel" placeholder="+ country code and number"></label>
        <label>Email (optional)<input name="email" type="email" maxlength="254" autocomplete="email"></label></div>
        <div class="grid"><label>Employment<select name="segment"><option>SALARIED</option><option>SELF_EMPLOYED</option><option>OTHER</option></select></label>
        <label>Preferred language<select name="preferred_language"><option>English</option><option>Hindi</option></select></label></div>
        <label class="check"><input type="checkbox" name="consent_calls" value="true">I permit service calls about this relationship.</label>
        <label class="check"><input type="checkbox" name="consent_marketing" value="true">I permit marketing messages.</label>
        <label class="check"><input type="checkbox" name="dnd" value="true">Do not contact me.</label>
        <label>Permission reference / request note<input name="consent_reference" maxlength="300" placeholder="Your requested contact purpose or permission reference"></label>
        <button type="submit">Submit application for review</button></form></section>'''
    elif purpose == "ONBOARDING":
        forms = '<section><h2>Application received</h2><p>Your application is in the staff review workflow. Refresh this private link to check its status.</p></section>'
    else:
        preferences = view.get("preferences", view.get("contact", customer))
        if not isinstance(preferences, dict):
            preferences = {}
        cases = view.get("cases", [])
        rows = "".join(f'<li><strong>{_safe(case.get("subject", "Service request"))}</strong><span>{_safe(case.get("status", "OPEN"))}</span></li>'
                       for case in cases[:50] if isinstance(case, dict))
        history = f'<ul class="cases">{rows}</ul>' if rows else '<p class="muted">No service requests yet.</p>'
        forms = f'''<section><h2>{_safe(name)}</h2><p class="muted">Customer {_safe(cid)}</p>
        <div class="grid"><div>Service calls<br><strong>{"Permitted" if preferences.get("consent_calls") else "Not permitted"}</strong></div>
        <div>Marketing<br><strong>{"Permitted" if preferences.get("consent_marketing") else "Not permitted"}</strong></div></div></section>
        <section><h2>Ask your relationship team</h2><form method="post" action="{action}">{hidden}
        <input type="hidden" name="request_type" value="CASE"><label>Request type<select name="category">
        <option value="SERVICE">Service enquiry</option><option value="COMPLAINT">Complaint</option>
        <option value="HARDSHIP">Repayment support</option><option value="DOCUMENTS">Documents</option>
        <option value="CONTACT_UPDATE">Contact update request</option></select></label>
        <label>Subject<input name="subject" required maxlength="150"></label>
        <label>Your message<textarea name="description" required maxlength="2000" rows="4"></textarea></label>
        <button type="submit">Send service request</button></form></section>
        <section><h2>Contact preferences</h2><p>You can withdraw permission here. Renewed permission requires a separate staff verification.</p>
        <form method="post" action="{action}">{hidden}<input type="hidden" name="request_type" value="CONTACT_PREFERENCES">
        <label class="check"><input type="checkbox" name="stop_calls" value="true">Stop service calls</label>
        <label class="check"><input type="checkbox" name="stop_marketing" value="true">Stop marketing messages</label>
        <button type="submit">Save withdrawals</button></form>
        <form method="post" action="{action}" class="separate">{hidden}<input type="hidden" name="request_type" value="OPT_OUT">
        <button type="submit" class="secondary">Stop all contact</button></form></section>
        <section><h2>Your service requests</h2>{history}</section>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="referrer" content="no-referrer"><title>Samvaad 360 · {_safe(title)}</title>
    <style>body{{margin:0;background:#f5f8f6;color:#183d33;font:16px/1.6 system-ui,sans-serif}}main{{max-width:800px;margin:40px auto;padding:0 20px}}
    header{{background:#153f32;color:#fff;border-radius:20px;padding:28px}}header p{{color:#d6e5db}}h1{{font-size:30px;line-height:1.2}}h2{{font-size:21px}}
    section{{background:white;border:1px solid #dbe5df;border-radius:14px;padding:24px;margin:18px 0}}.muted{{color:#637c70}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
    label{{display:block;margin:14px 0 6px}}input,select,textarea{{box-sizing:border-box;width:100%;padding:11px;border:1px solid #c5d6cc;border-radius:8px;font:inherit;background:#fff}}
    .check{{display:flex;gap:10px;align-items:center}}.check input{{width:auto}}button{{background:#176f51;color:white;border:0;border-radius:9px;padding:12px 20px;font:inherit;font-weight:600;cursor:pointer;margin-top:12px}}
    button:hover{{background:#12563e}}.secondary{{background:#f0f5f2;color:#234c3c;border:1px solid #c5d6cc}}.separate{{border-top:1px solid #e5ece7;margin-top:20px}}
    .notice{{padding:15px 20px;background:#dff1e6;border-radius:12px;margin:20px 0}}.cases{{padding:0;list-style:none}}.cases li{{display:flex;justify-content:space-between;gap:16px;padding:14px 0;border-bottom:1px solid #e4ece7}}
    footer{{font-size:13px;color:#637c70;padding:20px 0}}@media(max-width:560px){{main{{margin:20px auto}}.grid{{grid-template-columns:1fr}}section{{padding:18px}}h1{{font-size:26px}}}}</style></head>
    <body><main><header><strong>samvaad360</strong><h1>{_safe(title)}</h1><p>A private link for your application and relationship requests.</p></header>{flash}{summary}{forms}
    <footer>Controlled pilot · This link grants access to its own application or customer only. Keep it private. Staff review and strong identity verification remain separate steps.</footer></main></body></html>'''


def build_relationship_router(service, actor, relationship=None):
    hub = relationship or RelationshipService(service)
    router = APIRouter()

    @router.get("/api/relationship/status")
    def status(current=Depends(actor)):
        return hub.status(current)

    @router.get("/api/relationship/onboardings")
    def onboardings(current=Depends(actor)):
        return hub.list_onboardings(current)

    @router.post("/api/relationship/onboardings")
    async def onboard(request: Request, current=Depends(actor)):
        return hub.submit_onboarding(await _object(request), current, _key(request))

    @router.post("/api/relationship/onboardings/{onboarding_id}/review")
    async def review(onboarding_id: str, request: Request, current=Depends(actor)):
        body = await _object(request)
        _fields(body, {"decision", "note"}, {"decision"})
        return hub.review_onboarding(onboarding_id, body["decision"], body.get("note", ""), current)

    @router.post("/api/relationship/onboarding-invitations")
    def onboarding_invite(request: Request, current=Depends(actor)):
        return hub.issue_onboarding_invite(current, _key(request))

    @router.post("/api/relationship/onboardings/{onboarding_id}/attest")
    async def attest(onboarding_id: str, request: Request, current=Depends(actor)):
        body = await _object(request)
        _fields(body, {"identity_review", "document_review", "note"}, {"identity_review", "document_review", "note"})
        return hub.attest_onboarding(onboarding_id, body["identity_review"], body["document_review"], body["note"], current)

    @router.get("/api/relationship/customers/{customer_id}")
    def customer(customer_id: str, current=Depends(actor)):
        return hub.customer_relationship(customer_id, current)

    @router.post("/api/relationship/customers/{customer_id}/cases")
    async def case(customer_id: str, request: Request, current=Depends(actor)):
        return hub.add_case(customer_id, await _object(request), current, _key(request))

    @router.post("/api/relationship/cases/{case_id}/decision")
    async def decide_case(case_id: str, request: Request, current=Depends(actor)):
        body = await _object(request)
        _fields(body, {"status", "note"}, {"status"})
        return hub.update_case(case_id, body["status"], body.get("note", ""), current)

    @router.post("/api/relationship/customers/{customer_id}/portal-invitations")
    def invite(customer_id: str, request: Request, current=Depends(actor)):
        return hub.issue_portal_invite(customer_id, current, _key(request))

    @router.get("/api/relationship/sync/runs")
    def runs(current=Depends(actor)):
        return hub.list_sync_runs(current)

    @router.post("/api/relationship/sync/preview")
    async def preview(request: Request, current=Depends(actor)):
        body = await _object(request, 1048576)
        _fields(body, {"source", "records"}, {"source", "records"})
        return hub.preview_sync(body["source"], body["records"], current, _key(request))

    @router.post("/api/relationship/sync/customer-links")
    async def source_link(request: Request, current=Depends(actor)):
        body = await _object(request)
        _fields(body, {"source", "source_record_id", "customer_id", "note"}, {"source", "source_record_id", "customer_id", "note"})
        return hub.link_source_customer(body["source"], body["source_record_id"], body["customer_id"], current, _key(request), body["note"])

    @router.get("/api/relationship/sync/runs/{run_id}")
    def run(run_id: str, current=Depends(actor)):
        return hub.sync_run(run_id, current)

    @router.post("/api/relationship/sync/runs/{run_id}/commit")
    def commit(run_id: str, current=Depends(actor)):
        return hub.commit_sync(run_id, current)

    @router.get("/api/relationship/outbox")
    def outbox(current=Depends(actor)):
        return hub.outbox_status(current)

    @router.get("/portal/{token}", response_class=HTMLResponse)
    def portal(token: str):
        return HTMLResponse(_portal_page(hub.portal_view(token), token))

    @router.post("/portal/{token}/submit", response_class=HTMLResponse)
    async def submit_portal(token: str, request: Request):
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
            raise HTTPException(415, "Use the private portal form.")
        # Check the capability before reading its body.
        hub.portal_view(token)
        try:
            values = parse_qs((await _read(request, 8192)).decode("utf-8"), strict_parsing=True,
                              max_num_fields=24, keep_blank_values=True)
        except (ValueError, UnicodeError):
            raise HTTPException(422, "Invalid portal form.") from None
        if any(len(value) != 1 for value in values.values()):
            raise HTTPException(422, "Duplicate portal fields are not permitted.")
        data = {name: value[0] for name, value in values.items()}
        event_id = data.pop("event_id", "")
        if not re.fullmatch(r"portal:[0-9a-f]{32}", event_id):
            raise HTTPException(422, "Invalid portal request identifier.")
        kind = data.get("request_type")
        if kind == "APPLY":
            _fields(data, {"request_type", "full_name", "city", "monthly_income", "phone", "email", "segment",
                           "preferred_language", "consent_calls", "consent_marketing", "dnd", "consent_reference"}, {"full_name"})
            for name in ("consent_calls", "consent_marketing", "dnd"):
                if data.get(name, "false") not in {"true", "false"}:
                    raise HTTPException(422, "Invalid contact preference.")
                data[name] = data.get(name) == "true"
            try:
                data["monthly_income"] = float(data.get("monthly_income", "0"))
            except ValueError:
                raise HTTPException(422, "Monthly income must be a finite nonnegative amount.") from None
        elif kind == "CASE":
            _fields(data, {"request_type", "category", "subject", "description"}, {"subject", "description"})
        elif kind == "CONTACT_PREFERENCES":
            _fields(data, {"request_type", "stop_calls", "stop_marketing"})
            data = {"request_type": kind}
            if values.get("stop_calls") == ["true"]:
                data["consent_calls"] = False
            if values.get("stop_marketing") == ["true"]:
                data["consent_marketing"] = False
            if len(data) == 1:
                raise HTTPException(422, "Select at least one permission to withdraw.")
        elif kind == "OPT_OUT":
            _fields(data, {"request_type"})
        else:
            raise HTTPException(422, "Unsupported portal request.")
        hub.portal_submit(token, data, event_id)
        return HTMLResponse(_portal_page(hub.portal_view(token), token, "Your request was saved. Refreshing or retrying the same request does not create a duplicate."))

    return router, hub
