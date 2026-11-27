from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class RazorpayError(Exception):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class RazorpayClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RazorpayError("Razorpay Test Mode is not configured.")
        if not settings.razorpay_key_id.startswith("rzp_test_"):
            raise RazorpayError("Only Razorpay Test Mode credentials are accepted.")
        self._key_id = settings.razorpay_key_id
        self._key_secret = settings.razorpay_key_secret.get_secret_value()

    async def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url="https://api.razorpay.com/v1",
                auth=(self._key_id, self._key_secret),
                timeout=httpx.Timeout(12.0, connect=5.0),
            ) as client:
                response = await client.request(method, path, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning("razorpay_request_timeout", extra={"method": method, "path": path})
            raise RazorpayError("Razorpay did not respond before the request timed out.", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "razorpay_request_rejected",
                extra={"method": method, "path": path, "status_code": exc.response.status_code},
            )
            raise RazorpayError(
                "Razorpay rejected the request. Check the Test Mode account configuration."
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("razorpay_request_failed", extra={"method": method, "path": path})
            raise RazorpayError("Razorpay is temporarily unavailable.", retryable=True) from exc
        except ValueError as exc:
            raise RazorpayError("Razorpay returned an invalid response.") from exc
        if not isinstance(data, dict):
            raise RazorpayError("Razorpay returned an invalid response.")
        return data

    async def create_customer(
        self,
        *,
        name: str,
        email: str,
        contact: str | None,
        organization_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name[:100],
            "email": email,
            "fail_existing": 0,
            "notes": {"organization_id": organization_id},
        }
        if contact:
            payload["contact"] = contact[:20]
        return await self.request("POST", "/customers", payload=payload)

    async def create_plan(self) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/plans",
            payload={
                "period": "monthly",
                "interval": 1,
                "item": {
                    "name": "DM Karo Monthly",
                    "amount": 29900,
                    "currency": "INR",
                    "description": "DM Karo monthly subscription",
                },
            },
        )

    async def create_subscription(
        self,
        *,
        plan_id: str,
        organization_id: str,
        local_subscription_id: str,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            "/subscriptions",
            payload={
                "plan_id": plan_id,
                "total_count": 1200,
                "quantity": 1,
                "customer_notify": True,
                "notes": {
                    "organization_id": organization_id,
                    "dm_karo_subscription_id": local_subscription_id,
                },
            },
        )

    async def fetch_subscription(self, subscription_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/subscriptions/{subscription_id}")

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/payments/{payment_id}")

    async def cancel_subscription(
        self,
        subscription_id: str,
        *,
        cancel_at_cycle_end: bool,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
            payload={"cancel_at_cycle_end": cancel_at_cycle_end},
        )


def get_razorpay_client(settings: Settings) -> RazorpayClient:
    return RazorpayClient(settings)


def verify_checkout_signature(
    key_secret: str,
    subscription_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    expected = hmac.new(
        key_secret.encode("utf-8"),
        f"{subscription_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


_local_lock_guard = asyncio.Lock()
_local_locks: dict[str, asyncio.Lock] = {}


async def lock_billing_resource(session: Any, resource_key: str) -> None:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(resource_key.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        from sqlalchemy import text

        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        return
    async with _local_lock_guard:
        lock = _local_locks.setdefault(resource_key, asyncio.Lock())
    await lock.acquire()
    session.sync_session.info.setdefault("billing_locks", []).append(lock)


def release_local_billing_locks(session: Any) -> None:
    for lock in session.sync_session.info.pop("billing_locks", []):
        if lock.locked():
            lock.release()
