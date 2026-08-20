import hashlib
import hmac

from fastapi import Header, HTTPException, status

from .config import get_settings


def safe_equal(left: str, right: str) -> bool:
    return bool(left and right) and hmac.compare_digest(left.encode(), right.encode())


def require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_settings().bridge_service_token
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not safe_equal(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


def identifier_hash(identifier: str, secret: str) -> str:
    return hmac.new(secret.encode(), identifier.encode(), hashlib.sha256).hexdigest()
