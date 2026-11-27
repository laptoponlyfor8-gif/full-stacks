import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings

_password_hasher = PasswordHasher()


def _jwt_secret(settings: Settings) -> str:
    secret = settings.jwt_secret_key.get_secret_value()
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )
    return secret


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_password_hasher.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        return await run_in_threadpool(
            _password_hasher.verify,
            password_hash,
            password,
        )
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_hash_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def new_jti() -> str:
    return secrets.token_urlsafe(32)


def hash_token_identifier(identifier: str) -> str:
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()


def create_signed_token(
    settings: Settings,
    *,
    subject: UUID,
    token_use: str,
    expires_at: datetime,
    token_id: str | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    jti = token_id or new_jti()
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": str(subject),
        "jti": jti,
        "token_use": token_use,
        "iat": now,
        "exp": expires_at,
    }
    if extra_claims:
        claims.update(extra_claims)
    token = jwt.encode(claims, _jwt_secret(settings), algorithm="HS256")
    return token, jti


def decode_signed_token(settings: Settings, token: str, token_use: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(settings),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
        )
        if claims.get("token_use") != token_use:
            raise jwt.InvalidTokenError("Unexpected token purpose.")
        UUID(claims["sub"])
        if not isinstance(claims["jti"], str) or not claims["jti"]:
            raise jwt.InvalidTokenError("Invalid token identifier.")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The authentication token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def access_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)


def refresh_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_days)


def reset_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=settings.password_reset_token_minutes)


def verification_expiry(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(hours=settings.email_verification_token_hours)


def has_expired(value: datetime) -> bool:
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized <= datetime.now(UTC)
