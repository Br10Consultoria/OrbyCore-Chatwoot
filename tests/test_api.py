import os

os.environ.update(
    {
        "BRIDGE_SERVICE_TOKEN": "service-token-with-at-least-24-chars",
        "CHATWOOT_WEBHOOK_TOKEN": "webhook-token-with-at-least-24-chars",
        "CHATWOOT_INBOX_IDENTIFIER": "website-token",
        "CHATWOOT_INBOX_HMAC_TOKEN": "hmac-token",
        "MOBILE_SESSION_HMAC_SECRET": "mobile-session-secret-with-at-least-32-chars",
    }
)

from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.config import get_settings
from app.clients import UpstreamError
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


def _mobile_session_token() -> str:
    response = client.post(
        "/v1/portal/mobile/sessions",
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
    assert body["identity"]["identifier"] == "orby:tenant-1:customer-1"
    assert body["expires_at"] == body["identity_expires_at"]
    return body["session_token"]


def test_mobile_proxies_require_a_signed_mobile_session():
    response = client.get("/v1/mobile/autoservice/invoices/open")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_mobile_proxies_reject_a_session_with_an_altered_signature():
    token = _mobile_session_token()
    altered_token = f"{token[:-1]}{'a' if token[-1] != 'a' else 'b'}"
    response = client.get(
        "/v1/mobile/autoservice/invoices/open",
        headers={"Authorization": f"Bearer {altered_token}"},
    )
    assert response.status_code == 401


def test_mobile_invoice_proxy_derives_the_customer_from_the_session(monkeypatch):
    invoices = AsyncMock(return_value={"invoices": [{"id": "invoice-1"}]})
    monkeypatch.setattr("app.main.OrbyCoreClient.open_invoices", invoices)

    response = client.get(
        "/v1/mobile/autoservice/invoices/open",
        headers={"Authorization": f"Bearer {_mobile_session_token()}"},
    )

    assert response.status_code == 200
    assert response.json()["invoices"][0]["id"] == "invoice-1"
    invoices.assert_awaited_once_with("tenant-1", "customer-1")


def test_mobile_equipment_proxy_derives_the_customer_from_the_session(monkeypatch):
    devices = AsyncMock(return_value={"equipment": [{"id": "ont-1"}]})
    monkeypatch.setattr("app.main.OrbyCoreClient.devices", devices)

    response = client.get(
        "/v1/mobile/autoservice/equipment",
        headers={"Authorization": f"Bearer {_mobile_session_token()}"},
    )

    assert response.status_code == 200
    devices.assert_awaited_once_with("tenant-1", "customer-1")


def test_mobile_proxy_hides_upstream_error_details(monkeypatch):
    invoices = AsyncMock(side_effect=UpstreamError("Upstream respondeu HTTP 500 com detalhe sensível"))
    monkeypatch.setattr("app.main.OrbyCoreClient.open_invoices", invoices)
    response = client.get(
        "/v1/mobile/autoservice/invoices/open",
        headers={"Authorization": f"Bearer {_mobile_session_token()}"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "Não foi possível consultar as faturas"
    assert "sensível" not in response.text


def test_mobile_wifi_proxy_never_accepts_customer_or_tenant_from_the_app(monkeypatch, caplog):
    change_wifi = AsyncMock(return_value={"accepted": True, "command_id": "acs-1"})
    monkeypatch.setattr("app.main.OrbyCoreClient.change_wifi", change_wifi)

    response = client.patch(
        "/v1/mobile/autoservice/equipment/wifi",
        headers={"Authorization": f"Bearer {_mobile_session_token()}"},
        json={
            "device_id": "ont-1",
            "network": "5ghz",
            "ssid": "MinhaRede",
            "password": "senha-segura-123",
            "tenant_id": "tentativa-de-forjar",
            "customer_id": "tentativa-de-forjar",
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    change_wifi.assert_awaited_once_with(
        {
            "device_id": "ont-1",
            "network": "5ghz",
            "ssid": "MinhaRede",
            "password": "senha-segura-123",
            "tenant_id": "tenant-1",
            "customer_id": "customer-1",
        }
    )
    assert "senha-segura-123" not in caplog.text


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
