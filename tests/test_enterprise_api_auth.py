from fastapi.testclient import TestClient

from samvaad.service import LocalService
from webhook.main import create_app


def test_malformed_bearer_token_rejected_without_server_error(tmp_path):
    service = LocalService(tmp_path / "auth.db")
    app = create_app(service, token_map={"isolated-private-operator-token": "arjun"})
    client = TestClient(app, raise_server_exceptions=False)
    for token in [b"Bearer \xc3\xa9malformed-token", b"Bearer " + b"x" * 513]:
        response = client.get("/api/telephony/status", headers={"Authorization": token})
        assert response.status_code == 401
    assert client.get("/api/telephony/status", headers={"Authorization": "Bearer isolated-private-operator-token"}).json()["pilot_ready"] is False
