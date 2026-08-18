import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from redis.asyncio import Redis

from .automation import process_automation
from .clients import OrbyCoreClient, UpstreamError
from .config import get_settings
from .schemas import ChatwootWebhook, PortalIdentityRequest, WifiChangeRequest
from .security import identifier_hash, require_service_token, safe_equal


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    yield


app = FastAPI(
    title="OrbyCore Chatwoot Bridge",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/portal/identity", dependencies=[Depends(require_service_token)])
async def portal_identity(payload: PortalIdentityRequest) -> dict[str, str | int]:
    settings = get_settings()
    if not settings.chatwoot_inbox_identifier or not settings.chatwoot_inbox_hmac_token:
        raise HTTPException(status_code=503, detail="Inbox Chatwoot ainda não configurada")
    identifier = f"orby:{payload.tenant_id}:{payload.customer_id}"
    return {
        "base_url": settings.frontend_url,
        "website_token": settings.chatwoot_inbox_identifier,
        "identifier": identifier,
        "identifier_hash": identifier_hash(identifier, settings.chatwoot_inbox_hmac_token),
        "name": payload.name,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "expires_in": 300,
    }


@app.post("/v1/portal/wifi", dependencies=[Depends(require_service_token)])
async def change_wifi(payload: WifiChangeRequest) -> dict:
    try:
        return await OrbyCoreClient(get_settings()).change_wifi(payload.model_dump(exclude_none=True))
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Falha ao solicitar alteração Wi-Fi") from exc


@app.post("/v1/chatwoot/webhooks/{token}", status_code=status.HTTP_202_ACCEPTED)
async def chatwoot_webhook(token: str, payload: ChatwootWebhook, request: Request) -> dict[str, str]:
    settings = get_settings()
    if not safe_equal(token, settings.chatwoot_webhook_token):
        raise HTTPException(status_code=401, detail="Webhook inválido")
    if payload.id is not None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            first_delivery = await redis.set(f"chatwoot:event:{payload.id}", "1", ex=86400, nx=True)
        finally:
            await redis.aclose()
        if not first_delivery:
            return {"status": "accepted", "result": "duplicate"}
    result = await process_automation(payload.model_dump(), settings)
    return {"status": "accepted", "result": result}
