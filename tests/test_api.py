"""HTTP boundary acceptance checks using an isolated database and test-only tokens."""

import importlib
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


TOKENS = {
    "test-analyst-token-more-than-24-chars": "meera",
    "test-manager-token-more-than-24-chars": "arjun",
    "test-credit-token-more-than-24-chars": "kavya",
    "test-runner-token-more-than-24-chars": "local-runner",
}


@pytest.fixture
def client(service, monkeypatch, tmp_path):
    # Factory imports are side-effect free; keep DB env isolated as a precaution.
    monkeypatch.setenv("SAMVAAD_DB_PATH", str(tmp_path / "module-api.sqlite3"))
    module = importlib.import_module("webhook.main")
    with TestClient(module.create_app(service=service, token_map=TOKENS), raise_server_exceptions=False) as client:
        yield client


def auth(user):
    token = next(token for token, user_id in TOKENS.items() if user_id == user)
    return {"Authorization": f"Bearer {token}"}


def test_health_discloses_local_simulation_and_disabled_external_delivery(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "local-synthetic"
    assert response.json()["external_delivery"] is False
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/customers", "/api/portfolio", "/api/actions", "/api/offers", "/api/audit"])
def test_operator_data_requires_authentication(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_configured_token_resolves_fixed_identity(client):
    response = client.get("/api/me", headers=auth("meera"))
    assert response.status_code == 200
    assert response.json() == {"user_id": "meera", "role": "ANALYST"}


def test_api_retention_workflow_enforces_roles_and_approval(client, service):
    queued = client.post("/api/customers/C0002/recommend", headers=auth("meera"))
    assert queued.status_code == 200
    action_id = queued.json()["action_id"]
    forbidden = client.post(f"/api/actions/{action_id}/approve", headers=auth("meera"), json={"decision": "APPROVE"})
    assert forbidden.status_code == 403
    assert client.post(f"/api/actions/{action_id}/execute", headers=auth("local-runner"), json={"mode": "simulate", "outcome": "ACCEPT"}).status_code == 409
    assert not service.offers()
    assert client.post(f"/api/actions/{action_id}/approve", headers=auth("arjun"), json={"decision": "APPROVE"}).status_code == 200
    assert client.post(f"/api/actions/{action_id}/execute", headers=auth("local-runner"), json={"mode": "simulate", "outcome": "ACCEPT"}).status_code == 200
    retained = next(a for a in service.actions() if a["action_id"] == action_id)
    assert retained["status"] == "COMPLETED"


def test_body_cannot_impersonate_approver_or_enable_live_delivery(client):
    queued = client.post("/api/customers/C0002/recommend", headers=auth("meera")).json()
    action_id = queued["action_id"]
    response = client.post(f"/api/actions/{action_id}/approve", headers=auth("meera"), json={"decision": "APPROVE", "user_id": "arjun", "role": "MANAGER"})
    assert response.status_code == 422
    response = client.post(f"/api/actions/{action_id}/execute", headers=auth("local-runner"), json={"mode": "live", "outcome": "ACCEPT"})
    assert response.status_code == 422


def test_public_offer_is_scoped_and_duplicate_response_is_idempotent(client, service, analyst, credit, runner):
    action = service.recommend("C0003", analyst)
    service.approve_action(action["action_id"], credit)
    service.execute_action(action["action_id"], runner)
    offer = service.offers("C0003")[0]
    page = client.get(f"/offer/{offer['token']}")
    assert page.status_code == 200
    assert "synthetic" in page.text.lower()
    assert "10.75" not in page.text  # Ananya's evidence is never leaked into Imran's link.
    assert client.get("/offer/unknown-token").status_code == 404
    response_data = {"outcome": "ACCEPT", "event_id": "offer:" + "a" * 32}
    assert client.post(f"/offer/{offer['token']}/respond", data=response_data).status_code == 200
    count = len(service.audit(action_id=action["action_id"]))
    assert client.post(f"/offer/{offer['token']}/respond", data=response_data).status_code == 200
    assert len(service.audit(action_id=action["action_id"])) == count


def test_invalid_public_offer_form_is_rejected(client, service, analyst, credit, runner):
    action = service.recommend("C0003", analyst)
    service.approve_action(action["action_id"], credit)
    service.execute_action(action["action_id"], runner)
    token = service.offers("C0003")[0]["token"]
    assert client.post(f"/offer/{token}/respond", json={"outcome": "ACCEPT"}).status_code == 415
    assert client.post(f"/offer/{token}/respond", data={"outcome": "OPT_OUT", "event_id": "bad"}).status_code == 422


def test_api_maps_expired_invitation_to_gone_without_response_effect(
    client, service, analyst, credit, runner, monkeypatch
):
    import samvaad.service as service_module

    action = service.recommend("C0003", analyst)
    service.approve_action(action["action_id"], credit)
    service.execute_action(action["action_id"], runner)
    offer = service.offers("C0003")[0]
    expiry = datetime.fromisoformat(offer["expires_at"].replace("Z", "+00:00"))
    # Both the read path and atomic token-response transaction use this clock.
    monkeypatch.setattr(service_module, "utcnow", lambda: expiry + timedelta(seconds=1))
    count = len(service.audit(action_id=action["action_id"]))
    assert client.get(f"/offer/{offer['token']}").status_code == 410
    assert client.post(f"/offer/{offer['token']}/respond", data={"outcome": "ACCEPT", "event_id": "offer:" + "b" * 32}).status_code == 410
    assert len(service.audit(action_id=action["action_id"])) == count


def test_invitation_page_escapes_dynamic_customer_and_term_text(
    client, service, analyst, credit, runner, monkeypatch
):
    action = service.recommend("C0003", analyst)
    service.approve_action(action["action_id"], credit)
    service.execute_action(action["action_id"], runner)
    offer = service.offers("C0003")[0]
    original_get_offer = service.get_offer

    def malicious_record(token):
        record = original_get_offer(token)
        return {**record, "customer_name": "<script>alert('name')</script>",
                "offer": {"note": "<img src=x onerror=alert('terms')>"}}

    monkeypatch.setattr(service, "get_offer", malicious_record)
    response = client.get(f"/offer/{offer['token']}")
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "<img src=x" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "&lt;img" in response.text
