from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.clients import BaseClient, ChatwootClient, UpstreamError
from app.config import get_settings


@pytest.mark.asyncio
async def test_network_error_is_normalized_for_automation_fallback():
    request = httpx.Request("GET", "https://orbycore.invalid/api")
    with patch(
        "httpx.AsyncClient.request",
        new=AsyncMock(side_effect=httpx.ConnectError("offline", request=request)),
    ):
        with pytest.raises(UpstreamError, match="Falha de rede"):
            await BaseClient(get_settings()).request("GET", str(request.url))


@pytest.mark.asyncio
async def test_interactive_message_is_explicitly_sent_as_agent_bot():
    settings = get_settings().model_copy(update={"chatwoot_agent_bot_id": 17})
    response = httpx.Response(
        200,
        json={
            "content_type": "input_select",
            "content_attributes": {"items": [{"title": "Suporte", "value": "support"}]},
        },
    )
    with patch("httpx.AsyncClient.request", new=AsyncMock(return_value=response)) as request:
        await ChatwootClient(settings).send_message(
            10,
            "Escolha",
            content_type="input_select",
            content_attributes={"items": [{"title": "Suporte", "value": "support"}]},
        )

    payload = request.await_args.kwargs["json"]
    assert payload["sender_type"] == "AgentBot"
    assert payload["sender_id"] == 17
