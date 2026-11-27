import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

OAUTH_STATE_TTL_SECONDS = 600
PENDING_PAGE_TTL_SECONDS = 600
_META_TIMEOUT_SECONDS = 12.0


class MetaProviderError(Exception):
    def __init__(self, *, invalid_token: bool = False) -> None:
        super().__init__("The Meta authorization request could not be completed.")
        self.invalid_token = invalid_token


def _encryption_key(settings: Settings) -> bytes:
    encoded = settings.meta_token_encryption_key.get_secret_value()
    if not encoded:
        raise RuntimeError("Meta token encryption is not configured.")
    return base64.urlsafe_b64decode(encoded.encode("ascii"))


def encrypt_token(settings: Settings, token: str, *, context: str = "") -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_encryption_key(settings)).encrypt(
        nonce,
        token.encode("utf-8"),
        context.encode("utf-8"),
    )
    return "v1:" + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")


def decrypt_token(settings: Settings, encrypted_token: str, *, context: str = "") -> str:
    version, separator, payload = encrypted_token.partition(":")
    if version != "v1" or not separator:
        raise ValueError("The stored Meta token uses an unsupported encryption format.")
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, ciphertext = decoded[:12], decoded[12:]
        if len(nonce) != 12 or not ciphertext:
            raise ValueError
        token = AESGCM(_encryption_key(settings)).decrypt(
            nonce,
            ciphertext,
            context.encode("utf-8"),
        )
        return token.decode("utf-8")
    except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("The stored Meta token could not be decrypted.") from exc


def account_token_context(
    organization_id: UUID,
    platform: str,
    platform_account_id: str,
) -> str:
    return f"social-account:{organization_id}:{platform}:{platform_account_id}"


def make_oauth_state(
    *,
    user_id: UUID,
    organization_id: UUID,
    platform: str,
) -> tuple[str, str]:
    state = secrets.token_urlsafe(32)
    payload = json.dumps(
        {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "platform": platform,
        },
        separators=(",", ":"),
    )
    return state, payload


def build_authorization_url(
    settings: Settings,
    *,
    platform: str,
    state: str,
) -> str:
    if not settings.meta_app_id or not settings.meta_redirect_uri:
        raise RuntimeError("Meta OAuth is not configured.")

    if platform == "instagram":
        params = {
            "client_id": settings.meta_app_id,
            "redirect_uri": settings.meta_redirect_uri,
            "response_type": "code",
            "scope": (
                "instagram_business_basic,"
                "instagram_business_manage_comments,"
                "instagram_business_manage_messages"
            ),
            "state": state,
            "enable_fb_login": "0",
            "force_authentication": "1",
        }
        return "https://www.instagram.com/oauth/authorize?" + urlencode(params)

    if platform == "facebook":
        if not settings.meta_facebook_login_config_id:
            raise RuntimeError("Facebook Login for Business is not configured.")
        params = {
            "client_id": settings.meta_app_id,
            "redirect_uri": settings.meta_redirect_uri,
            "response_type": "code",
            "config_id": settings.meta_facebook_login_config_id,
            "override_default_response_type": "true",
            "state": state,
        }
        return (
            f"https://www.facebook.com/{settings.meta_graph_api_version}/dialog/oauth?"
            + urlencode(params)
        )
    raise ValueError("Unsupported Meta platform.")


def state_key(state: str) -> str:
    return "meta-oauth-state:" + hashlib.sha256(state.encode("utf-8")).hexdigest()


def pending_pages_key(flow_id: str) -> str:
    return "meta-oauth-pages:" + hashlib.sha256(flow_id.encode("utf-8")).hexdigest()


async def _meta_request(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=_META_TIMEOUT_SECONDS) as client:
            response = await client.request(method, url, params=params, data=data)
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MetaProviderError from exc

    if not isinstance(body, dict):
        raise MetaProviderError
    error = body.get("error")
    if response.is_error or error:
        error_code = error.get("code") if isinstance(error, dict) else None
        raise MetaProviderError(invalid_token=error_code == 190)
    return body


def _required_token(payload: dict[str, Any]) -> str:
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise MetaProviderError
    return token


async def connect_instagram(
    settings: Settings,
    code: str,
) -> tuple[str, str, str | None, str, datetime | None]:
    if not settings.meta_app_id or not settings.meta_app_secret or not settings.meta_redirect_uri:
        raise RuntimeError("Meta OAuth is not configured.")
    secret = settings.meta_app_secret.get_secret_value()
    short_token_data = await _meta_request(
        "POST",
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": settings.meta_app_id,
            "client_secret": secret,
            "grant_type": "authorization_code",
            "redirect_uri": settings.meta_redirect_uri,
            "code": code,
        },
    )
    short_token = _required_token(short_token_data)
    long_token_data = await _meta_request(
        "GET",
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": secret,
            "access_token": short_token,
        },
    )
    long_token = _required_token(long_token_data)
    profile = await _meta_request(
        "GET",
        f"https://graph.instagram.com/{settings.meta_graph_api_version}/me",
        params={
            "fields": "user_id,username,account_type",
            "access_token": long_token,
        },
    )
    platform_account_id = profile.get("user_id")
    account_name = profile.get("username")
    account_type = profile.get("account_type")
    if (
        not isinstance(platform_account_id, (str, int))
        or not str(platform_account_id)
        or not isinstance(account_name, str)
        or not account_name.strip()
    ):
        raise MetaProviderError
    expires_in = long_token_data.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
        if isinstance(expires_in, int) and expires_in > 0
        else None
    )
    return str(platform_account_id), account_name.strip(), account_type, long_token, expires_at


async def refresh_instagram_token(
    settings: Settings,
    access_token: str,
) -> tuple[str, datetime | None]:
    payload = await _meta_request(
        "GET",
        "https://graph.instagram.com/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": access_token,
        },
    )
    token = _required_token(payload)
    expires_in = payload.get("expires_in")
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
        if isinstance(expires_in, int) and expires_in > 0
        else None
    )
    return token, expires_at


async def list_facebook_pages(
    settings: Settings,
    code: str,
) -> list[dict[str, Any]]:
    if not settings.meta_app_id or not settings.meta_app_secret or not settings.meta_redirect_uri:
        raise RuntimeError("Meta OAuth is not configured.")
    user_token_data = await _meta_request(
        "GET",
        f"https://graph.facebook.com/{settings.meta_graph_api_version}/oauth/access_token",
        params={
            "client_id": settings.meta_app_id,
            "client_secret": settings.meta_app_secret.get_secret_value(),
            "redirect_uri": settings.meta_redirect_uri,
            "code": code,
        },
    )
    user_token = _required_token(user_token_data)
    app_access_token = (
        f"{settings.meta_app_id}|{settings.meta_app_secret.get_secret_value()}"
    )
    safe_pages: list[dict[str, Any]] = []
    after: str | None = None
    seen_cursors: set[str] = set()
    pages_url = (
        f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/accounts"
    )
    for _ in range(100):
        params = {"fields": "id,name,access_token", "access_token": user_token}
        if after:
            params["after"] = after
        page_response = await _meta_request("GET", pages_url, params=params)
        data = page_response.get("data")
        if not isinstance(data, list):
            raise MetaProviderError
        for page in data:
            if not isinstance(page, dict):
                continue
            page_id = page.get("id")
            name = page.get("name")
            page_token = page.get("access_token")
            if (
                isinstance(page_id, (str, int))
                and str(page_id)
                and isinstance(name, str)
                and name.strip()
                and isinstance(page_token, str)
                and page_token
            ):
                safe_pages.append(
                    {
                        "id": str(page_id),
                        "name": name.strip(),
                        "access_token": page_token,
                    }
                )
        paging = page_response.get("paging")
        next_page = paging.get("next") if isinstance(paging, dict) else None
        if not next_page:
            return safe_pages
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        cursor = cursors.get("after") if isinstance(cursors, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            raise MetaProviderError
        seen_cursors.add(cursor)
        after = cursor
    raise MetaProviderError


async def inspect_facebook_page_token(
    settings: Settings,
    access_token: str,
) -> datetime | None:
    if not settings.meta_app_id or not settings.meta_app_secret:
        raise RuntimeError("Meta app credentials are not configured.")
    app_access_token = (
        f"{settings.meta_app_id}|{settings.meta_app_secret.get_secret_value()}"
    )
    payload = await _meta_request(
        "GET",
        f"https://graph.facebook.com/{settings.meta_graph_api_version}/debug_token",
        params={
            "input_token": access_token,
            "access_token": app_access_token,
        },
    )
    metadata = payload.get("data")
    if not isinstance(metadata, dict) or metadata.get("is_valid") is not True:
        raise MetaProviderError(invalid_token=True)
    expires_at = metadata.get("expires_at")
    if isinstance(expires_at, int) and expires_at > 0:
        return datetime.fromtimestamp(expires_at, UTC)
    return None


async def subscribe_account_webhooks(
    settings: Settings,
    *,
    platform: str,
    platform_account_id: str,
    access_token: str,
) -> None:
    if platform == "instagram":
        host = "graph.instagram.com"
        fields = "comments,messages"
    elif platform == "facebook":
        host = "graph.facebook.com"
        fields = "feed,messages"
    else:
        raise ValueError("Unsupported Meta platform.")
    result = await _meta_request(
        "POST",
        f"https://{host}/{settings.meta_graph_api_version}/{platform_account_id}/subscribed_apps",
        data={"subscribed_fields": fields, "access_token": access_token},
    )
    if result.get("success") is not True:
        raise MetaProviderError()


async def resolve_content_id(
    settings: Settings,
    *,
    platform: str,
    platform_account_id: str,
    access_token: str,
    permalink: str,
) -> str:
    from urllib.parse import urlsplit

    def normalized_url(value: str) -> tuple[str, str] | None:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        return parsed.hostname.lower(), parsed.path.rstrip("/")

    wanted = normalized_url(permalink)
    if wanted is None:
        raise ValueError("Content URL must be a valid HTTPS permalink.")
    if platform == "instagram":
        host, edge, fields = "graph.instagram.com", "media", "id,permalink"
    elif platform == "facebook":
        host, edge, fields = "graph.facebook.com", "posts", "id,permalink_url"
    else:
        raise ValueError("Unsupported Meta platform.")
    url = f"https://{host}/{settings.meta_graph_api_version}/{platform_account_id}/{edge}"
    after: str | None = None
    seen: set[str] = set()
    for _ in range(20):
        params = {
            "fields": fields,
            "limit": "100",
            "access_token": access_token,
        }
        if after:
            params["after"] = after
        response = await _meta_request("GET", url, params=params)
        data = response.get("data")
        if not isinstance(data, list):
            raise MetaProviderError()
        for item in data:
            if not isinstance(item, dict):
                continue
            item_url = item.get("permalink_url") or item.get("permalink")
            item_id = item.get("id")
            if (
                isinstance(item_url, str)
                and normalized_url(item_url) == wanted
                and isinstance(item_id, (str, int))
                and str(item_id)
            ):
                return str(item_id)
        paging = response.get("paging")
        cursors = paging.get("cursors") if isinstance(paging, dict) else None
        cursor = cursors.get("after") if isinstance(cursors, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            break
        seen.add(cursor)
        after = cursor
    raise ValueError("The permalink was not found in this connected account's recent content.")
