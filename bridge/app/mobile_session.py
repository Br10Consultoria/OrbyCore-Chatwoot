import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status

from .config import get_settings
from .security import safe_equal


MOBILE_AUDIENCE = "sac-mobile"


@dataclass(frozen=True)
class MobilePrincipal:
    tenant_id: str
    customer_id: str
    name: str
    email: str
    phone_number: str


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _json_segment(value: dict) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def issue_mobile_session(principal: MobilePrincipal) -> tuple[str, str]:
    settings = get_settings()
    if not settings.mobile_session_hmac_secret:
        raise HTTPException(status_code=503, detail="Sessão móvel ainda não configurada")

    now = int(time.time())
    expires_at = now + settings.mobile_session_ttl_seconds
    header = _json_segment({"alg": "HS256", "typ": "JWT"})
    payload = _json_segment(
        {
            "aud": MOBILE_AUDIENCE,
            "cid": principal.customer_id,
            "email": principal.email,
            "exp": expires_at,
            "iat": now,
            "iss": settings.mobile_session_issuer,
            "jti": secrets.token_urlsafe(18),
            "name": principal.name,
            "phone_number": principal.phone_number,
            "sub": f"orby:{principal.tenant_id}:{principal.customer_id}",
            "tid": principal.tenant_id,
        }
    )
    signed_value = f"{header}.{payload}"
    signature = _b64encode(
        hmac.new(settings.mobile_session_hmac_secret.encode(), signed_value.encode(), hashlib.sha256).digest()
    )
    return f"{signed_value}.{signature}", datetime.fromtimestamp(expires_at, timezone.utc).isoformat()


def _invalid_mobile_session() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão móvel inválida ou expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_mobile_session(authorization: str | None = Header(default=None)) -> MobilePrincipal:
    settings = get_settings()
    if not settings.mobile_session_hmac_secret:
        raise HTTPException(status_code=503, detail="Sessão móvel ainda não configurada")

    token = authorization.removeprefix("Bearer ") if authorization else ""
    parts = token.split(".")
    if len(parts) != 3:
        raise _invalid_mobile_session()
    header, payload, supplied_signature = parts
    expected_signature = _b64encode(
        hmac.new(
            settings.mobile_session_hmac_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
    )
    if not safe_equal(supplied_signature, expected_signature):
        raise _invalid_mobile_session()
    try:
        parsed_header = json.loads(_b64decode(header))
        claims = json.loads(_b64decode(payload))
        expires_at = int(claims["exp"])
        issued_at = int(claims["iat"])
        principal = MobilePrincipal(
            tenant_id=str(claims["tid"]),
            customer_id=str(claims["cid"]),
            name=str(claims["name"]),
            email=str(claims.get("email", "")),
            phone_number=str(claims.get("phone_number", "")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise _invalid_mobile_session() from None
    if (
        parsed_header != {"alg": "HS256", "typ": "JWT"}
        or claims.get("iss") != settings.mobile_session_issuer
        or claims.get("aud") != MOBILE_AUDIENCE
        or expires_at <= int(time.time())
        or issued_at > int(time.time()) + 60
        or not principal.tenant_id
        or not principal.customer_id
    ):
        raise _invalid_mobile_session()
    return principal
