import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from redis.asyncio import Redis

from .clients import OrbyCoreClient, UpstreamError
from .config import get_settings
from .queue import enqueue_webhook
from .mobile_session import MobilePrincipal, issue_mobile_session, require_mobile_session
from .schemas import (
    ChatwootWebhook,
    MobileWifiChangeRequest,
    PortalIdentityRequest,
    PortalMobileSessionRequest,
    WifiChangeRequest,
)
from .security import identifier_hash, require_service_token, safe_equal


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    application.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await application.state.redis.aclose()


app = FastAPI(
    title="OrbyCore Chatwoot Bridge",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request) -> dict[str, str]:
    settings = get_settings()
    if not settings.chatwoot_api_token or not settings.orbycore_service_token:
        raise HTTPException(status_code=503, detail="Integração ainda não configurada")
    try:
        await request.app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis indisponível") from exc
    return {"status": "ready"}


@app.post("/v1/portal/identity", dependencies=[Depends(require_service_token)])
async def portal_identity(payload: PortalIdentityRequest) -> dict[str, str | int]:
    return _identity_for(payload)


def _identity_for(payload: PortalIdentityRequest) -> dict[str, str | int]:
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


@app.post("/v1/portal/mobile/sessions", dependencies=[Depends(require_service_token)])
async def create_mobile_session(payload: PortalMobileSessionRequest) -> dict:
    """Emite sessão curta apenas para o Portal SAC já autenticado no servidor."""
    principal = MobilePrincipal(
        tenant_id=payload.tenant_id,
        customer_id=payload.customer_id,
        name=payload.name,
        email=payload.email,
        phone_number=payload.phone_number,
    )
    session_token, expires_at = issue_mobile_session(principal)
    identity = _identity_for(payload)
    return {
        "session_token": session_token,
        "expires_at": expires_at,
        "identity": identity,
        "identity_expires_at": expires_at,
    }


@app.post("/v1/portal/wifi", dependencies=[Depends(require_service_token)])
async def change_wifi(payload: WifiChangeRequest) -> dict:
    try:
        return await OrbyCoreClient(get_settings()).change_wifi(
            payload.model_dump(exclude_none=True)
        )
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Falha ao solicitar alteração Wi-Fi") from exc


@app.get("/v1/mobile/autoservice/invoices/open")
async def mobile_open_invoices(principal: MobilePrincipal = Depends(require_mobile_session)) -> dict:
    try:
        return await OrbyCoreClient(get_settings()).open_invoices(
            principal.tenant_id, principal.customer_id
        )
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível consultar as faturas") from exc


@app.get("/v1/mobile/autoservice/equipment")
async def mobile_equipment(principal: MobilePrincipal = Depends(require_mobile_session)) -> dict:
    try:
        return await OrbyCoreClient(get_settings()).devices(principal.tenant_id, principal.customer_id)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Não foi possível consultar os equipamentos") from exc


@app.patch("/v1/mobile/autoservice/equipment/wifi")
async def mobile_change_wifi(
    payload: MobileWifiChangeRequest, principal: MobilePrincipal = Depends(require_mobile_session)
) -> dict:
    logging.getLogger(__name__).info(
        "mobile_wifi_change tenant=%s customer=%s device=%s network=%s",
        principal.tenant_id,
        principal.customer_id,
        payload.device_id,
        payload.network,
    )
    try:
        return await OrbyCoreClient(get_settings()).change_wifi(
            {
                **payload.model_dump(exclude_none=True),
                "tenant_id": principal.tenant_id,
                "customer_id": principal.customer_id,
            }
        )
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail="Falha ao solicitar alteração Wi-Fi") from exc


@app.post("/v1/chatwoot/webhooks/{token}", status_code=status.HTTP_202_ACCEPTED)
async def chatwoot_webhook(
    token: str, payload: ChatwootWebhook, request: Request
) -> dict[str, str]:
    settings = get_settings()
    if not safe_equal(token, settings.chatwoot_webhook_token):
        raise HTTPException(status_code=401, detail="Webhook inválido")
    account_id = payload.account.get("id")
    if payload.event == "message_created" and account_id is None:
        raise HTTPException(status_code=403, detail="Conta Chatwoot ausente")
    if account_id is not None:
        try:
            account_matches = int(account_id) == settings.chatwoot_account_id
        except (TypeError, ValueError):
            account_matches = False
        if not account_matches:
            raise HTTPException(status_code=403, detail="Conta Chatwoot não autorizada")
    conversation_inbox_id = payload.conversation.get("inbox_id")
    inbox_id = conversation_inbox_id or payload.inbox.get("id")
    if payload.event == "message_created" and inbox_id is None:
        raise HTTPException(status_code=403, detail="Inbox Chatwoot ausente")
    if inbox_id is not None:
        try:
            inbox_matches = int(inbox_id) == settings.chatwoot_inbox_id
        except (TypeError, ValueError):
            inbox_matches = False
        if not inbox_matches:
            raise HTTPException(status_code=403, detail="Inbox Chatwoot não autorizado")
    queued = await enqueue_webhook(request.app.state.redis, payload.model_dump())
    return {"status": "accepted", "result": "queued" if queued else "duplicate"}
