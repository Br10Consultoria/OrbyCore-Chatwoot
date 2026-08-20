import os

os.environ.update(
    {
        "BRIDGE_SERVICE_TOKEN": "service-token-with-at-least-24-chars",
        "CHATWOOT_WEBHOOK_TOKEN": "webhook-token-with-at-least-24-chars",
        "CHATWOOT_INBOX_IDENTIFIER": "website-token",
        "CHATWOOT_INBOX_HMAC_TOKEN": "hmac-token",
    }
)

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.config import get_settings
from app.main import app

get_settings.cache_clear()
client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_identity_requires_service_token():
    response = client.post(
        "/v1/portal/identity",
        json={"tenant_id": "t", "customer_id": "c", "name": "Cliente"},
    )
    assert response.status_code == 401


def test_identity_is_derived_from_server_payload():
    response = client.post(
        "/v1/portal/identity",
        headers={"Authorization": "Bearer service-token-with-at-least-24-chars"},
        json={
            "tenant_id": "tenant-1",
            "customer_id": "customer-1",
            "name": "Cliente Teste",
            "email": "cliente@example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["identifier"] == "orby:tenant-1:customer-1"
    assert len(body["identifier_hash"]) == 64
    assert "hmac-token" not in response.text


def test_webhook_rejects_another_chatwoot_account():
    response = client.post(
        "/v1/chatwoot/webhooks/webhook-token-with-at-least-24-chars",
        json={"event": "message_created", "id": 1, "account": {"id": 999}},
    )
    assert response.status_code == 403


def test_webhook_is_queued_and_returns_immediately(monkeypatch):
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr("app.main.enqueue_webhook", enqueue)
    app.state.redis = object()
    response = client.post(
        "/v1/chatwoot/webhooks/webhook-token-with-at-least-24-chars",
        json={
            "event": "message_created",
            "id": 2,
            "account": {"id": 1},
            "conversation": {"inbox_id": 1},
        },
    )
    assert response.status_code == 202
    assert response.json()["result"] == "queued"
    enqueue.assert_awaited_once()
