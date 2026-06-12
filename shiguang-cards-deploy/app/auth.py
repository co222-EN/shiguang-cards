from __future__ import annotations

import hmac
import time
from hashlib import sha256

from fastapi import HTTPException, Request

from .config import settings


COOKIE_NAME = "shiguang_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 45


def _sign(payload: str) -> str:
    return hmac.new(settings.session_secret.encode(), payload.encode(), sha256).hexdigest()


def create_session_token() -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"personal:{expires}"
    return f"{payload}.{_sign(payload)}"


def verify_session_token(token: str | None) -> bool:
    if not settings.app_passcode:
        return True
    if not token or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload), signature):
        return False
    try:
        _, expires = payload.split(":", 1)
        return int(expires) > int(time.time())
    except ValueError:
        return False


def require_session(request: Request) -> None:
    if not verify_session_token(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="需要先解锁拾光卡片")
