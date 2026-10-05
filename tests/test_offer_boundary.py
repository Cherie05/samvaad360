"""Capability and transaction checks for public synthetic offer responses."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from samvaad.models import ActionError
from webhook.main import create_app


TOKENS = {
    "test-analyst-token-more-than-24-chars": "meera",
    "test-manager-token-more-than-24-chars": "arjun",
    "test-runner-token-more-than-24-chars": "local-runner",
}


def ready_offer(service, customer_id="C0003"):
    action = service.recommend(customer_id, service.resolve_actor("meera"))
    approver = "kavya" if customer_id == "C0003" else "arjun"
    service.approve_action(action["action_id"], service.resolve_actor(approver))
    service.execute_action(action["action_id"], service.resolve_actor("local-runner"))
    return service.offers(customer_id)[0]


def test_exact_opt_out_replay_succeeds_without_more_audit_and_blocks_new_accept(service):
    offer = ready_offer(service)
    first = service.respond_to_offer(offer["token"], "OPT_OUT", "optout-event-1")
    assert first["action"]["status"] == "CANCELLED"
    assert first["offer"]["status"] == "REVOKED"
    before = service.audit()
    second = service.respond_to_offer(offer["token"], "OPT_OUT", "optout-event-1")
    assert second["replayed"] is True
    assert service.audit() == before
    with pytest.raises(ActionError) as error:
        service.respond_to_offer(offer["token"], "ACCEPT", "new-accept-event")
    assert error.value.code == "OFFER_REVOKED"
    assert service.audit() == before
    assert not service.customer360("C0003")["customer"]["consent_calls"]
    assert offer["token"] not in json.dumps(service.audit())


def test_http_opt_out_replay_succeeds_while_revoked_get_and_new_responses_are_gone(service):
    offer = ready_offer(service)
    route = f"/offer/{offer['token']}"
    data = {"outcome": "OPT_OUT", "event_id": "offer:" + "b" * 32}
    with TestClient(create_app(service, TOKENS), raise_server_exceptions=False) as client:
        assert client.post(route + "/respond", data=data).status_code == 200
        count = len(service.audit())
        assert client.get(route).status_code == 410
        assert client.post(route + "/respond", data=data).status_code == 200
        assert len(service.audit()) == count
        assert client.post(route + "/respond", data={"outcome": "ACCEPT", "event_id": "offer:" + "c" * 32}).status_code == 410


def test_expiration_wins_over_prior_event_replay_for_get_and_post(service):
    offer = ready_offer(service)
    route = f"/offer/{offer['token']}"
    data = {"outcome": "OPT_OUT", "event_id": "offer:" + "d" * 32}
    with TestClient(create_app(service, TOKENS), raise_server_exceptions=False) as client:
        assert client.post(route + "/respond", data=data).status_code == 200
        with service._db(write=True) as con:
            con.execute("UPDATE offers SET expires_at=? WHERE offer_id=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), offer["offer_id"]))
        before = service.audit()
        assert client.get(route).status_code == 410
        assert client.post(route + "/respond", data=data).status_code == 410
        assert service.audit() == before


def test_event_cannot_be_reused_with_another_offer_or_changed_outcome(service):
    first, second = ready_offer(service, "C0002"), ready_offer(service, "C0003")
    service.respond_to_offer(first["token"], "DECLINE", "fixed-client-event")
    before = service.audit()
    second_before = service.customer360("C0003")
    with pytest.raises(ActionError) as error:
        service.respond_to_offer(second["token"], "OPT_OUT", "fixed-client-event")
    assert error.value.code == "EVENT_CONFLICT"
    with pytest.raises(ActionError) as error:
        service.respond_to_offer(first["token"], "ACCEPT", "fixed-client-event")
    assert error.value.code == "EVENT_CONFLICT"
    second_after = service.customer360("C0003")
    for key in ("customer", "loans", "payments", "interactions", "actions"):
        if key in second_before:
            assert second_after[key] == second_before[key]
    assert service.audit() == before
    assert service.get_offer(second["token"])["status"] == "ACCEPTED"


def test_same_effective_outcome_still_binds_event_identity(service):
    offer = ready_offer(service)
    first = service.respond_to_offer(offer["token"], "ACCEPT", "same-preference-event")
    assert first["action"]["outcome"] == "ACCEPT"
    assert service.respond_to_offer(offer["token"], "ACCEPT", "same-preference-event")["replayed"]
    with pytest.raises(ActionError) as error:
        service.respond_to_offer(offer["token"], "DECLINE", "same-preference-event")
    assert error.value.code == "EVENT_CONFLICT"


def test_concurrent_duplicate_opt_out_is_one_effect_and_one_replay(service):
    offer = ready_offer(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.respond_to_offer, offer["token"], "OPT_OUT", "concurrent-event") for _ in range(2)]
        values = [future.result(timeout=15) for future in futures]
    assert sorted(value["replayed"] for value in values) == [False, True]
    events = service.audit(action_id=offer["action_id"])
    assert sum(event["event"] == "CUSTOMER_RESPONSE" and event["detail"].get("event_id") == "concurrent-event" for event in events) == 1
    assert not service.customer360("C0003")["customer"]["consent_calls"]


def test_local_interaction_http_route_respects_fixed_analyst_identity(service):
    body = {"channel": "EMAIL", "text": "I am planning a balance transfer because the rate is too high."}
    with TestClient(create_app(service, TOKENS), raise_server_exceptions=False) as client:
        route = "/api/customers/C0002/interactions"
        assert client.post(route, json=body).status_code == 401
        assert client.post(route, json=body, headers={"Authorization": "Bearer test-manager-token-more-than-24-chars"}).status_code == 403
        response = client.post(route, json=body, headers={"Authorization": "Bearer test-analyst-token-more-than-24-chars"})
        assert response.status_code == 200
        assert response.json()["customer_id"] == "C0002"
        assert response.json()["intent"] == "balance transfer or foreclosure"
        assert response.json()["text"] == body["text"]
