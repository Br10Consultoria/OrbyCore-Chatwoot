from typing import Any

import httpx

from .config import Settings


class UpstreamError(RuntimeError):
    pass


class BaseClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise UpstreamError(f"Falha de rede ao acessar {exc.request.url.host}") from exc
        if response.status_code >= 400:
            raise UpstreamError(f"Upstream respondeu HTTP {response.status_code}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("Upstream retornou JSON inválido") from exc


class ChatwootClient(BaseClient):
    @property
    def headers(self) -> dict[str, str]:
        return {"api_access_token": self.settings.chatwoot_api_token}

    async def send_message(self, conversation_id: int, content: str) -> Any:
        url = (
            f"{self.settings.chatwoot_api_url.rstrip('/')}/api/v1/accounts/"
            f"{self.settings.chatwoot_account_id}/conversations/{conversation_id}/messages"
        )
        return await self.request(
            "POST",
            url,
            headers=self.headers,
            json={"content": content, "message_type": "outgoing", "private": False},
        )


class OrbyCoreClient(BaseClient):
    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.orbycore_service_token}"}

    async def open_invoices(self, tenant_id: str, customer_id: str) -> Any:
        url = (
            f"{self.settings.orbycore_api_url.rstrip('/')}/api/v1/integrations/chatwoot/"
            f"customers/{customer_id}/invoices/open/"
        )
        return await self.request("GET", url, headers={**self.headers, "X-Tenant-ID": tenant_id})

    async def devices(self, tenant_id: str, customer_id: str) -> Any:
        url = (
            f"{self.settings.orbycore_api_url.rstrip('/')}/api/v1/integrations/chatwoot/"
            f"customers/{customer_id}/equipment/"
        )
        return await self.request("GET", url, headers={**self.headers, "X-Tenant-ID": tenant_id})

    async def change_wifi(self, payload: dict[str, Any]) -> Any:
        url = (
            f"{self.settings.orbycore_api_url.rstrip('/')}/api/v1/integrations/chatwoot/"
            f"customers/{payload['customer_id']}/equipment/{payload['device_id']}/wifi/"
        )
        return await self.request(
            "PATCH",
            url,
            headers={**self.headers, "X-Tenant-ID": payload["tenant_id"]},
            json=payload,
        )
