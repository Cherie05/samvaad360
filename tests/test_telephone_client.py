import io
import json
from urllib.error import HTTPError, URLError

import pytest

from public_app.telephony_client import NoRedirects, TelephoneClient, TelephoneUnavailable, operator_token


TOKEN = "isolated-test-operator-token-123456789"


def test_staff_identity_requires_verified_subject_and_live_expiry():
    settings = {"operator_tokens": {"https://issuer.example|staff-1": TOKEN}}
    claims = {"is_logged_in": True, "email_verified": True, "exp": 2000,
              "iss": "https://issuer.example", "sub": "staff-1"}
    assert operator_token(claims, settings, now=1000) == TOKEN
    for changed in ({"is_logged_in": False}, {"email_verified": "true"}, {"exp": 999},
                    {"exp": float("inf")}, {"exp": True}, {"sub": "another-staff"}, {"iss": "https://attacker.example"}):
        assert operator_token({**claims, **changed}, settings, now=1000) is None


@pytest.mark.parametrize("url", ["http://api.example", "https://user:password@api.example", "file:///tmp/key",
                                  "https://api.example/redirect", "https://api.example?token=secret"])
def test_bridge_rejects_unreviewed_api_origins(url):
    with pytest.raises(TelephoneUnavailable):
        TelephoneClient(url, TOKEN)


class Transport:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.requests = response, error, []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(json.dumps(self.response).encode())


def test_auth_and_acknowledged_call_are_server_request_only():
    transport = Transport({"call_id": "call-1", "status": "DISPATCHING"})
    client = TelephoneClient("https://api.example", TOKEN, opener=transport)
    result = client.start_call(action_id="action-1", recipient_id="recipient-1", idempotency_key="intent-1", acknowledged_live_call=True)
    request, timeout = transport.requests[0]
    assert request.get_header("Authorization") == "Bearer " + TOKEN
    assert json.loads(request.data)["acknowledged_live_call"] is True
    assert timeout == 12
    assert TOKEN not in json.dumps(result)


def test_phone_api_failure_never_exposes_secret_provider_message():
    for error in [HTTPError("https://api.example", 403, TOKEN, {}, None), URLError(TOKEN)]:
        client = TelephoneClient("https://api.example", TOKEN, opener=Transport(error=error))
        with pytest.raises(TelephoneUnavailable) as failure:
            client.status()
        assert TOKEN not in str(failure.value)


def test_phone_record_path_cannot_escape_to_another_endpoint():
    transport = Transport({})
    client = TelephoneClient("https://api.example", TOKEN, opener=transport)
    with pytest.raises(TelephoneUnavailable):
        client.cancel_call("../../api/admin")
    assert transport.requests == []


def test_redirect_does_not_forward_operator_credentials():
    with pytest.raises(TelephoneUnavailable):
        NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://foreign.example")


@pytest.mark.parametrize("response", [{}, [], {"pilot_ready": "true", "production_ready": False}])
def test_carrier_readiness_is_not_inferred_from_an_arbitrary_response(response):
    client = TelephoneClient("https://api.example", TOKEN, opener=Transport(response))
    with pytest.raises(TelephoneUnavailable):
        client.status()


@pytest.mark.parametrize("response", [{}, {"call_id": "call-1"}, {"call_id": "call-1", "status": "connected-fictionally"}])
def test_call_success_is_not_inferred_from_an_arbitrary_response(response):
    client = TelephoneClient("https://api.example", TOKEN, opener=Transport(response))
    with pytest.raises(TelephoneUnavailable):
        client.start_call(action_id="action-1", recipient_id="recipient-1", idempotency_key="intent-1", acknowledged_live_call=True)
