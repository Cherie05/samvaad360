"""Authenticated staff telephone controls, separate from visit-local rehearsals."""
from __future__ import annotations

import os
from uuid import uuid4

import streamlit as st

from public_app.telephony_client import TelephoneClient, TelephoneUnavailable, operator_token


def render_telephone(view, admit_action):
    st.subheader("Telephone calling")
    st.caption("Use a verified existing number or an additional verified number through your configured carrier.")
    try:
        settings = dict(st.secrets.get("telephony", {}))
    except Exception:
        settings = {}
    if not settings.get("api_base_url") or settings.get("enabled") is not True:
        st.info("Telephone calling is awaiting carrier and staff-login setup. No phone call or SMS will be sent.")
        left, right = st.columns(2)
        with left:
            st.text_input("Existing customer number", value="Masked in this fictional portfolio", disabled=True)
        with right:
            st.text_input("Additional number", placeholder="Verify a permitted number after staff sign-in", disabled=True)
        st.button("Place telephone call", disabled=True, type="primary", key="telephone_unconfigured")
        st.caption("The telephone integration uses genuine carrier requests and signed callbacks. It does not generate a simulated connection.")
        return
    if not st.user.is_logged_in:
        st.info("Sign in as an authorised staff operator to access telephone numbers and calling.")
        if "auth" in st.secrets:
            st.button("Staff sign-in", on_click=st.login, key="telephone_login")
        else:
            st.caption("Staff authentication has not been configured by the administrator.")
        return
    claims = dict(st.user)
    claims["is_logged_in"] = st.user.is_logged_in
    token = operator_token(claims, settings)
    if token is None:
        st.warning("This identity is not authorised for telephone operations, or its session has expired.")
        return
    try:
        client = TelephoneClient(settings["api_base_url"], token,
                                 allow_local=os.getenv("SAMVAAD_ALLOW_LOCAL_TELEPHONY_API") == "1")
        status = client.status()
        ready = status.get("pilot_ready", False)
        if not ready:
            st.warning("Telephone setup is incomplete. Calling and number verification remain disabled.")
        st.caption("Carrier state is read from the telephone service. Network timeouts do not count as successful delivery.")
        cid = view["customer"]["customer_id"]
        recipients = client.recipients(cid)
        if isinstance(recipients, dict):
            recipients = recipients.get("recipients", [])
        with st.expander("Existing and additional numbers", expanded=not recipients):
            if recipients:
                st.dataframe([{k: r.get(k) for k in ("recipient_id", "source", "phone_masked", "verified", "verification_status")} for r in recipients],
                             hide_index=True, width="stretch")
            with st.form("telephone_recipient"):
                source = st.radio("Number source", ["Existing customer number", "Additional number"])
                phone = st.text_input("Permitted number in international format", max_chars=16, placeholder="+ country code and number")
                note = st.text_input("Recipient permission reference", max_chars=500)
                permission = st.checkbox("The recipient authorised this verification message and telephone pilot.")
                submitted = st.form_submit_button("Send verification code", disabled=not ready)
            if submitted:
                if not permission:
                    st.warning("Record recipient permission before sending a verification message.")
                elif admit_action():
                    result = client.register_recipient(customer_id=cid, phone=phone,
                        source="primary" if source == "Existing customer number" else "alternate",
                        consent_note=note, verification_requested=True)
                    st.session_state["telephone_pending_recipient"] = result.get("recipient_id")
                    st.success("Verification request accepted by the service. Check the provider-confirmed status.")
            pending = st.session_state.get("telephone_pending_recipient")
            if pending:
                with st.form("telephone_verify"):
                    code = st.text_input("Recipient verification code", type="password", max_chars=10)
                    verify = st.form_submit_button("Verify number", disabled=not ready)
                if verify and admit_action():
                    result = client.verify_recipient(pending, code)
                    if result.get("verified"):
                        st.success("The provider confirmed number possession. This does not replace borrower authentication.")
                        st.session_state.pop("telephone_pending_recipient", None)
                    else:
                        st.warning("Number verification was not confirmed.")
        verified = [r for r in recipients if r.get("verified")]
        actions = client.actions()
        if isinstance(actions, dict):
            actions = actions.get("actions", [])
        actions = [a for a in actions if a.get("customer_id") == cid and a.get("status") == "APPROVED"]
        if not verified or not actions:
            st.info("A provider-verified permitted number and an approved operational action are required. Public simulation reviews cannot authorise telephone calls.")
        else:
            action = st.selectbox("Approved telephone action", actions, format_func=lambda a: a.get("title", a["action_id"]))
            recipient = st.selectbox("Call destination", verified, format_func=lambda r: f'{r.get("source", "Number")} · {r.get("phone_masked", "Verified number")}')
            confirmed = st.checkbox("Place a real carrier call to this permitted test recipient.")
            intent_key = "telephone_intent_" + action["action_id"] + "_" + recipient["recipient_id"]
            if intent_key not in st.session_state:
                st.session_state[intent_key] = uuid4().hex
            if st.button("Place telephone call", type="primary", disabled=not ready or not confirmed, key="telephone_originate") and admit_action():
                result = client.start_call(action_id=action["action_id"], recipient_id=recipient["recipient_id"],
                                           idempotency_key=st.session_state[intent_key], acknowledged_live_call=True)
                st.session_state["telephone_last_call"] = result.get("call_id")
                st.info("Carrier request recorded. Connection, answer and completion are confirmed by provider events.")
        if st.button("Refresh carrier status", key="telephone_refresh") and admit_action():
            call_id = st.session_state.get("telephone_last_call")
            if call_id:
                client.reconcile_call(call_id)
        calls = client.calls()
        if isinstance(calls, dict):
            calls = calls.get("calls", [])
        calls = [c for c in calls if c.get("customer_id") == cid]
        if calls:
            st.dataframe([{k: c.get(k) for k in ("call_id", "status", "outcome", "created_at")} for c in calls], hide_index=True, width="stretch")
            current = st.session_state.get("telephone_last_call")
            recorded = next((c for c in calls if c.get("call_id") == current), None)
            if recorded and recorded.get("status") in {"failed", "busy", "no-answer", "canceled"}:
                if st.button("Prepare next permitted attempt", key="telephone_next_attempt", disabled=not ready) and admit_action():
                    next_intent = "telephone_intent_" + recorded["action_id"] + "_" + recorded["recipient_id"]
                    st.session_state[next_intent] = uuid4().hex
                    st.info("A new attempt is prepared. The service will recheck approval, consent, the four-hour delay and call budget before dialing.")
            elif recorded and st.button("Cancel telephone call", key="telephone_cancel") and admit_action():
                client.cancel_call(current)
                st.info("Cancellation was requested. Check the provider-confirmed final state.")
    except TelephoneUnavailable as error:
        st.error(str(error))
