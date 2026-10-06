"""Server-only staff bridge to a configured telephone API; never a simulator."""
from __future__ import annotations

import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class TelephoneUnavailable(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TelephoneUnavailable("The telephone API redirected the request. Contact your administrator.")


def operator_token(claims, settings, *, now=None):
    """Bind an OIDC issuer/subject to a server-stored, per-operator pilot token.

    These claims must come from st.user, never session state or a browser form.
    This single-tenant pilot bridge does not implement enterprise delegation.
    """
    if not claims.get("is_logged_in") or claims.get("email_verified") is not True:
        return None
    expiry = claims.get("exp")
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
        return None
    if expiry <= (time.time() if now is None else now):
        return None
    issuer, subject = claims.get("iss"), claims.get("sub")
    if not isinstance(issuer, str) or not issuer or not isinstance(subject, str) or not subject:
        return None
    tokens = settings.get("operator_tokens", {})
    token = tokens.get(issuer + "|" + subject) if isinstance(tokens, dict) else None
    return token if isinstance(token, str) and len(token) >= 24 else None


class TelephoneClient:
    def __init__(self, base_url, token, *, opener=None, allow_local=False):
        parts = urlsplit(str(base_url))
        local = allow_local and parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}
        if (parts.scheme != "https" and not local) or not parts.hostname or parts.username or parts.password:
            raise TelephoneUnavailable("Configure a trusted HTTPS telephone API.")
        if parts.query or parts.fragment or parts.path not in {"", "/"}:
            raise TelephoneUnavailable("The telephone API address must be an HTTPS origin.")
        if not isinstance(token, str) or len(token) < 24 or any(c in token for c in "\r\n"):
            raise TelephoneUnavailable("An authorised staff API credential is required.")
        self.base_url, self._token = str(base_url).rstrip("/"), token
        self._opener = opener or build_opener(NoRedirects())

    def _request(self, path, body=None):
        request = Request(self.base_url + path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"},
                          method="GET" if body is None else "POST")
        try:
            with self._opener.open(request, timeout=12) as response:
                raw = response.read(131073)
                if len(raw) > 131072:
                    raise TelephoneUnavailable("The telephone API response exceeded its limit.")
                result = json.loads(raw)
                if not isinstance(result, (dict, list)):
                    raise ValueError("Unsupported response")
                return result
        except HTTPError as error:
            messages = {401: "Your staff session is unauthorised.", 403: "This staff identity cannot perform that operation.",
                        409: "The call was held by a policy or replay check. Check its current state.",
                        429: "Telephone usage limit reached. Try again later.",
                        503: "The telephone provider is not configured or currently unavailable."}
            raise TelephoneUnavailable(messages.get(error.code, "The telephone API declined the operation.")) from None
        except (URLError, TimeoutError, OSError, ValueError) as error:
            if isinstance(error, TelephoneUnavailable):
                raise
            raise TelephoneUnavailable("The telephone API did not return a usable response. No successful call is assumed.") from None

    def status(self):
        value = self._request("/api/telephony/status")
        if not isinstance(value, dict) or not isinstance(value.get("pilot_ready"), bool) or not isinstance(value.get("production_ready"), bool):
            raise TelephoneUnavailable("The telephone service did not confirm its readiness.")
        return value

    def recipients(self, customer_id):
        return self._request("/api/telephony/recipients?" + urlencode({"customer_id": customer_id}))

    def register_recipient(self, **values):
        value = self._request("/api/telephony/recipients", values)
        self._record(value, "recipient_id")
        if value.get("verification_status") != "PENDING" or value.get("verified") is not False:
            raise TelephoneUnavailable("The service did not confirm a pending number verification.")
        return value

    def verify_recipient(self, recipient_id, code):
        value = self._request("/api/telephony/recipients/" + self._identifier(recipient_id) + "/verify", {"code": code})
        self._record(value, "recipient_id")
        if not isinstance(value.get("verified"), bool):
            raise TelephoneUnavailable("The service did not confirm number possession.")
        return value

    def actions(self):
        return self._request("/api/actions?status=APPROVED")

    def calls(self):
        return self._request("/api/telephony/calls")

    def start_call(self, **values):
        value = self._request("/api/telephony/calls", values)
        self._record(value, "call_id")
        if value.get("status") not in {"DISPATCHING", "DISPATCH_UNCERTAIN", "queued", "ringing", "in-progress", "completed", "failed", "busy", "no-answer", "canceled"}:
            raise TelephoneUnavailable("The service did not confirm a carrier request state. Check its records before retrying.")
        return value

    def cancel_call(self, call_id):
        return self._request("/api/telephony/calls/" + self._identifier(call_id) + "/cancel", {})

    def reconcile_call(self, call_id):
        return self._request("/api/telephony/calls/" + self._identifier(call_id) + "/reconcile", {})

    @staticmethod
    def _record(value, key):
        if not isinstance(value, dict):
            raise TelephoneUnavailable("The telephone service returned an unsupported record.")
        TelephoneClient._identifier(value.get(key))

    @staticmethod
    def _identifier(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 100 or not all(c.isalnum() or c in "_-" for c in value):
            raise TelephoneUnavailable("Choose a valid telephone record.")
        return value
