from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.clients import BaseClient, UpstreamError
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
