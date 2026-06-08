from __future__ import annotations
import base64
import hashlib
import hmac
import json
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import app.config as cfg

security = HTTPBearer(
    auto_error=False,
    description="Enter your JWT token using the format: Bearer <token>",
)


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def _get_jwt_secret() -> str:
    if not cfg.JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not configured")
    return cfg.JWT_SECRET


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_base64url_decode(header_b64))
        payload = json.loads(_base64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JWT encoding") from exc

    if header.get("alg") != "HS256":
        raise ValueError("Unsupported JWT algorithm")

    message = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    try:
        signature = _base64url_decode(signature_b64)
    except ValueError as exc:
        raise ValueError("Invalid JWT signature encoding") from exc

    if not hmac.compare_digest(expected_signature, signature):
        raise ValueError("Invalid JWT signature")

    return payload


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not cfg.AUTH_ENABLED:
        return "anonymous"

    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = _decode_jwt(token, cfg.JWT_SECRET)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("userId") or payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Token payload missing userId",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return str(user_id)
