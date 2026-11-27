from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import Principal, get_current_principal
from app.core.config import Settings
from app.db.session import get_db_session
from app.db.tenant import set_tenant_organization
from app.models import (
    BillingCustomer,
    BillingEventLog,
    BillingPlan,
    BillingWebhookEvent,
    Organization,
    Payment,
    Subscription,
    User,
)
from app.models.billing import OPEN_SUBSCRIPTION_STATUSES
from app.models.enums import OrganizationRole
from app.schemas.billing import (
    BillingOverviewResponse,
    BillingPlanResponse,
    CancellationRequest,
    CancellationResponse,
    CheckoutResponse,
    CheckoutVerificationRequest,
    CheckoutVerificationResponse,
    PaymentResponse,
    SubscriptionResponse,
)
from app.services.rate_limit import enforce_rate_limit
from app.services.razorpay import (
    RazorpayClient,
    RazorpayError,
    get_razorpay_client,
    lock_billing_resource,
    release_local_billing_locks,
    verify_checkout_signature,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])
webhook_router = APIRouter(prefix="/webhooks/razorpay", tags=["Razorpay webhooks"])

PLAN_CODE = "dm-karo-monthly"
PLAN_NAME = "DM Karo Monthly"
PLAN_AMOUNT = Decimal("299.00")
PLAN_SUBUNITS = 29900
PLAN_CURRENCY = "INR"
PROVIDER_SUBSCRIPTION_STATUSES = {
    "created",
    "authenticated",
    "active",
    "pending",
    "halted",
    "cancelled",
    "completed",
    "expired",
    "paused",
}
OPEN_PROVIDER_STATUSES = tuple(
    status_value
    for status_value in OPEN_SUBSCRIPTION_STATUSES
    if status_value not in {"creating", "creation_unknown"}
)
TERMINAL_STATUSES = {"cancelled", "completed", "expired"}


def _client(request: Request) -> RazorpayClient:
    configured = getattr(request.app.state, "razorpay_client", None)
    if configured is not None:
        return configured
    try:
        return get_razorpay_client(request.app.state.settings)
    except RazorpayError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay Test Mode is not configured on this server.",
        ) from exc


def _require_billing_admin(principal: Principal) -> None:
    if principal.role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can manage billing.",
        )


def _plan_response() -> BillingPlanResponse:
    return BillingPlanResponse()


def _provider_time(timestamp: Any) -> datetime | None:
    if not isinstance(timestamp, int) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, UTC)


async def _ensure_plan(
    session: AsyncSession,
    client: RazorpayClient,
) -> BillingPlan:
    await lock_billing_resource(session, "razorpay:dm-karo-monthly-plan")
    try:
        plan = await session.get(BillingPlan, PLAN_CODE)
        if plan is not None:
            await session.commit()
            if plan.provisioning_status == "ready" and plan.razorpay_plan_id:
                return plan
            raise RazorpayError(
                "The Razorpay plan setup is pending reconciliation; contact support before retrying."
            )
        plan = BillingPlan(
            code=PLAN_CODE,
            razorpay_plan_id=None,
            plan_name=PLAN_NAME,
            amount_subunits=PLAN_SUBUNITS,
            currency=PLAN_CURRENCY,
            provisioning_status="creating",
        )
        session.add(plan)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        release_local_billing_locks(session)

    try:
        response = await client.create_plan()
    except RazorpayError as exc:
        plan.provisioning_status = "creation_unknown" if exc.retryable else "creation_failed"
        if not exc.retryable:
            await session.delete(plan)
        await session.commit()
        raise
    plan_id = response.get("id")
    if not isinstance(plan_id, str) or not plan_id.startswith("plan_"):
        plan.provisioning_status = "creation_unknown"
        await session.commit()
        raise RazorpayError("Razorpay returned an incomplete plan response; contact support before retrying.")
    plan.razorpay_plan_id = plan_id
    plan.provisioning_status = "ready"
    await session.commit()
    return plan


async def _ensure_customer(
    session: AsyncSession,
    client: RazorpayClient,
    *,
    principal: Principal,
) -> str:
    organization_id = principal.organization_id
    await set_tenant_organization(session, organization_id)
    await lock_billing_resource(session, f"razorpay:customer:{organization_id}")
    try:
        customer = await session.scalar(
            select(BillingCustomer).where(
                BillingCustomer.organization_id == organization_id
            )
        )
        if customer is not None:
            await session.commit()
            return customer.razorpay_customer_id
        user = await session.scalar(select(User).where(User.id == principal.user_id))
        organization = await session.scalar(
            select(Organization).where(Organization.id == organization_id)
        )
        if user is None or organization is None:
            raise HTTPException(status_code=404, detail="Organization billing profile not found.")
        response = await client.create_customer(
            name=user.name,
            email=user.email,
            contact=user.mobile_number,
            organization_id=str(organization_id),
        )
        customer_id = response.get("id")
        if not isinstance(customer_id, str) or not customer_id.startswith("cust_"):
            raise RazorpayError("Razorpay did not return a valid customer identifier.")
        session.add(
            BillingCustomer(
                organization_id=organization_id,
                razorpay_customer_id=customer_id,
            )
        )
        await session.commit()
        return customer_id
    except Exception:
        await session.rollback()
        raise
    finally:
        release_local_billing_locks(session)


def _http_error(exc: RazorpayError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


@router.get("", response_model=BillingOverviewResponse)
async def get_billing_overview(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BillingOverviewResponse:
    _require_billing_admin(principal)
    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.organization_id == principal.organization_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    payments: list[Payment] = []
    if subscription:
        payments = list(
            (
                await session.scalars(
                    select(Payment)
                    .where(
                        Payment.organization_id == principal.organization_id,
                        Payment.subscription_id == subscription.id,
                    )
                    .order_by(Payment.created_at.desc())
                    .limit(50)
                )
            ).all()
        )
    return BillingOverviewResponse(
        plan=_plan_response(),
        subscription=SubscriptionResponse.model_validate(subscription) if subscription else None,
        payments=[PaymentResponse.model_validate(payment) for payment in payments],
    )


@router.post("/subscriptions", response_model=CheckoutResponse, status_code=201)
async def create_subscription(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutResponse:
    _require_billing_admin(principal)
    await enforce_rate_limit(
        request,
        action="billing-subscribe",
        limit=request.app.state.settings.auth_sensitive_rate_limit,
        identity=str(principal.organization_id),
    )
    client = _client(request)
    try:
        plan = await _ensure_plan(session, client)
        customer_id = await _ensure_customer(session, client, principal=principal)
    except RazorpayError as exc:
        raise _http_error(exc) from exc

    await set_tenant_organization(session, principal.organization_id)
    reservation = Subscription(
        organization_id=principal.organization_id,
        plan_name=PLAN_NAME,
        amount=PLAN_AMOUNT,
        currency=PLAN_CURRENCY,
        status="creating",
        razorpay_customer_id=customer_id,
        razorpay_plan_id=plan.razorpay_plan_id,
    )
    session.add(reservation)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        await set_tenant_organization(session, principal.organization_id)
        current = await session.scalar(
            select(Subscription).where(
                Subscription.organization_id == principal.organization_id,
                or_(
                    Subscription.status.in_(("creating", "creation_unknown")),
                    and_(
                        Subscription.razorpay_subscription_id.is_not(None),
                        Subscription.status.in_(OPEN_PROVIDER_STATUSES),
                    ),
                ),
            )
        )
        if current:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An existing subscription is already in progress or active.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The subscription could not be reserved; please try again.",
        ) from exc

    try:
        provider_subscription = await client.create_subscription(
            plan_id=plan.razorpay_plan_id,
            organization_id=str(principal.organization_id),
            local_subscription_id=str(reservation.id),
        )
    except RazorpayError as exc:
        await set_tenant_organization(session, principal.organization_id)
        reservation.status = "creation_unknown" if exc.retryable else "creation_failed"
        await session.commit()
        raise _http_error(exc) from exc

    provider_id = provider_subscription.get("id")
    provider_plan = provider_subscription.get("plan_id")
    if (
        not isinstance(provider_id, str)
        or not provider_id.startswith("sub_")
        or provider_plan != plan.razorpay_plan_id
    ):
        await set_tenant_organization(session, principal.organization_id)
        reservation.status = "creation_unknown"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay returned an incomplete subscription response; contact support before retrying.",
        )

    await set_tenant_organization(session, principal.organization_id)
    reservation.razorpay_subscription_id = provider_id
    reservation.status = (
        provider_subscription.get("status")
        if provider_subscription.get("status") in PROVIDER_SUBSCRIPTION_STATUSES
        else "created"
    )
    reservation.next_billing_at = _provider_time(provider_subscription.get("charge_at"))
    await session.commit()
    return CheckoutResponse(
        key_id=request.app.state.settings.razorpay_key_id,
        subscription_id=provider_id,
        checkout_url=provider_subscription.get("short_url"),
        status=reservation.status,
        plan=_plan_response(),
    )


@router.post("/checkout/verify", response_model=CheckoutVerificationResponse)
async def verify_checkout(
    payload: CheckoutVerificationRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CheckoutVerificationResponse:
    _require_billing_admin(principal)
    await enforce_rate_limit(
        request,
        action="billing-checkout-verify",
        limit=request.app.state.settings.auth_sensitive_rate_limit,
        identity=str(principal.organization_id),
    )
    settings: Settings = request.app.state.settings
    if not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay Test Mode is not configured.")
    if not verify_checkout_signature(
        settings.razorpay_key_secret.get_secret_value(),
        payload.razorpay_subscription_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
    ):
        logger.warning("razorpay_checkout_signature_rejected")
        raise HTTPException(status_code=400, detail="Payment verification failed.")

    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.organization_id == principal.organization_id,
            Subscription.razorpay_subscription_id == payload.razorpay_subscription_id,
        )
    )
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    client = _client(request)
    try:
        provider_payment, provider_subscription = await _fetch_checkout_state(
            client,
            payload.razorpay_payment_id,
            payload.razorpay_subscription_id,
        )
    except RazorpayError as exc:
        raise _http_error(exc) from exc

    notes = provider_subscription.get("notes")
    if (
        provider_payment.get("id") != payload.razorpay_payment_id
        or provider_payment.get("status") not in {"authorized", "captured"}
        or provider_subscription.get("id") != payload.razorpay_subscription_id
        or provider_subscription.get("plan_id") != subscription.razorpay_plan_id
        or not isinstance(notes, dict)
        or notes.get("organization_id") != str(principal.organization_id)
        or provider_payment.get("subscription_id") != payload.razorpay_subscription_id
    ):
        raise HTTPException(status_code=400, detail="Razorpay payment details did not match this subscription.")

    await _record_payment(
        session,
        organization_id=principal.organization_id,
        subscription=subscription,
        payment=provider_payment,
        start_at=None,
        end_at=None,
        provider_event_at=_provider_time(provider_payment.get("created_at")),
    )
    await session.commit()
    current_status = subscription.status
    return CheckoutVerificationResponse(
        verified=True,
        payment_status=str(provider_payment.get("status", "unknown")),
        subscription_status=current_status,
        message=(
            "Payment details were verified. Subscription access will update when Razorpay confirms activation."
            if current_status not in {"active"}
            else "Payment details were verified and Razorpay reports this subscription as active."
        ),
    )


async def _fetch_checkout_state(
    client: RazorpayClient,
    payment_id: str,
    subscription_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    import asyncio

    payment, subscription = await asyncio.gather(
        client.fetch_payment(payment_id),
        client.fetch_subscription(subscription_id),
    )
    return payment, subscription


@router.post(
    "/subscriptions/{subscription_id}/cancel",
    response_model=CancellationResponse,
)
async def cancel_subscription(
    subscription_id: UUID,
    payload: CancellationRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> CancellationResponse:
    _require_billing_admin(principal)
    await enforce_rate_limit(
        request,
        action="billing-cancel",
        limit=request.app.state.settings.auth_sensitive_rate_limit,
        identity=str(principal.organization_id),
    )
    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.organization_id == principal.organization_id,
        )
    )
    if subscription is None or not subscription.razorpay_subscription_id:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    if subscription.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="This subscription can no longer be changed.")
    try:
        provider_subscription = await _client(request).cancel_subscription(
            subscription.razorpay_subscription_id,
            cancel_at_cycle_end=payload.cancel_at_cycle_end,
        )
    except RazorpayError as exc:
        raise _http_error(exc) from exc
    if provider_subscription.get("id") != subscription.razorpay_subscription_id:
        raise HTTPException(status_code=502, detail="Razorpay returned an unexpected subscription.")
    subscription.cancel_at_cycle_end = payload.cancel_at_cycle_end
    subscription.cancellation_requested_at = datetime.now(UTC)
    if (
        provider_subscription.get("status") in TERMINAL_STATUSES
        or (
            not payload.cancel_at_cycle_end
            and provider_subscription.get("status") in PROVIDER_SUBSCRIPTION_STATUSES
        )
    ):
        subscription.status = provider_subscription["status"]
    await session.commit()
    return CancellationResponse(
        status=subscription.status,
        cancel_at_cycle_end=subscription.cancel_at_cycle_end,
        message=(
            "Cancellation is scheduled at the end of the current billing cycle."
            if payload.cancel_at_cycle_end
            else "Cancellation was requested. The subscription will close when Razorpay confirms it."
        ),
    )


@router.get("/payments", response_model=list[PaymentResponse])
async def get_payment_history(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_db_session),
) -> list[PaymentResponse]:
    _require_billing_admin(principal)
    payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(Payment.organization_id == principal.organization_id)
                .order_by(Payment.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return [PaymentResponse.model_validate(payment) for payment in payments]


@webhook_router.post("", status_code=200)
async def receive_razorpay_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    secret = settings.razorpay_webhook_secret
    if secret is None:
        raise HTTPException(status_code=503, detail="Razorpay webhook verification is not configured.")
    await _webhook_rate_limit(request)
    body = await _read_body(request, 262_144)
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_webhook_signature(secret.get_secret_value(), body, signature):
        logger.warning("razorpay_webhook_signature_rejected")
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc
    if not isinstance(envelope, dict) or not isinstance(envelope.get("event"), str):
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")
    event_type = envelope["event"]
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook payload.")
    subscription = _webhook_entity(payload, "subscription")
    payment = _webhook_entity(payload, "payment")
    if subscription is None:
        payment_subscription_id = payment.get("subscription_id") if payment else None
        if not isinstance(payment_subscription_id, str):
            return {"status": "ignored"}
        try:
            subscription = await _client(request).fetch_subscription(payment_subscription_id)
        except RazorpayError as exc:
            raise _http_error(exc) from exc
    provider_subscription_id = subscription.get("id")
    notes = subscription.get("notes")
    organization_value = notes.get("organization_id") if isinstance(notes, dict) else None
    try:
        organization_id = UUID(organization_value)
    except (ValueError, TypeError, AttributeError):
        logger.warning("razorpay_webhook_organization_missing")
        return {"status": "ignored"}
    if not isinstance(provider_subscription_id, str):
        return {"status": "ignored"}

    await set_tenant_organization(session, organization_id)
    local_subscription = await session.scalar(
        select(Subscription).where(
            Subscription.organization_id == organization_id,
            Subscription.razorpay_subscription_id == provider_subscription_id,
        )
    )
    local_subscription_id = notes.get("dm_karo_subscription_id") if isinstance(notes, dict) else None
    if local_subscription is None and isinstance(local_subscription_id, str):
        try:
            local_id = UUID(local_subscription_id)
        except ValueError:
            local_id = None
        if local_id is not None:
            local_subscription = await session.scalar(
                select(Subscription).where(
                    Subscription.id == local_id,
                    Subscription.organization_id == organization_id,
                    Subscription.status.in_(("creating", "creation_unknown")),
                )
            )
            if local_subscription is not None:
                local_subscription.razorpay_subscription_id = provider_subscription_id
    if local_subscription is None:
        logger.warning("razorpay_webhook_subscription_unmatched")
        return {"status": "ignored"}
    if subscription.get("plan_id") != local_subscription.razorpay_plan_id:
        logger.warning("razorpay_webhook_plan_mismatch")
        return {"status": "ignored"}
    event_id = request.headers.get("X-Razorpay-Event-Id")
    if not event_id:
        event_id = hashlib.sha256(body).hexdigest()
    if len(event_id) > 160:
        raise HTTPException(status_code=400, detail="Invalid webhook event identifier.")
    existing = await session.scalar(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.organization_id == organization_id,
            BillingWebhookEvent.razorpay_event_id == event_id,
        )
    )
    if existing is not None:
        await session.rollback()
        return {"status": "duplicate"}

    event_time = _provider_time(envelope.get("created_at")) or datetime.now(UTC)
    session.add(
        BillingWebhookEvent(
            organization_id=organization_id,
            razorpay_event_id=event_id,
            event_type=event_type[:100],
            razorpay_subscription_id=provider_subscription_id,
            processed_at=datetime.now(UTC),
            processing_status="processed",
        )
    )
    if payment is not None:
        await _record_payment(
            session,
            organization_id=organization_id,
            subscription=local_subscription,
            payment=payment,
            start_at=subscription.get("current_start"),
            end_at=subscription.get("current_end"),
            provider_event_at=event_time,
        )
    incoming_status = _status_from_event(event_type, subscription)
    last_event_time = local_subscription.last_provider_event_at
    if last_event_time is not None and last_event_time.tzinfo is None:
        last_event_time = last_event_time.replace(tzinfo=UTC)
    if (
        incoming_status is not None
        and (last_event_time is None or event_time > last_event_time)
        and local_subscription.status not in TERMINAL_STATUSES
    ):
        previous_status = local_subscription.status
        local_subscription.status = incoming_status
        local_subscription.last_provider_event_at = event_time
        local_subscription.razorpay_customer_id = (
            subscription.get("customer_id") or local_subscription.razorpay_customer_id
        )
        local_subscription.billing_start_at = (
            _provider_time(subscription.get("current_start")) or local_subscription.billing_start_at
        )
        local_subscription.billing_end_at = (
            _provider_time(subscription.get("current_end")) or local_subscription.billing_end_at
        )
        local_subscription.next_billing_at = _provider_time(subscription.get("charge_at"))
        if incoming_status in {"pending", "halted"}:
            local_subscription.grace_period_ends_at = event_time + timedelta(
                days=request.app.state.settings.billing_grace_period_days
            )
        elif incoming_status == "active":
            local_subscription.grace_period_ends_at = None
        if incoming_status == "cancelled":
            local_subscription.cancel_at_cycle_end = False
        session.add(
            BillingEventLog(
                organization_id=organization_id,
                subscription_id=local_subscription.id,
                event_type=event_type[:100],
                previous_status=previous_status,
                new_status=incoming_status,
                provider_event_id=event_id,
            )
        )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate"}
    return {"status": "accepted"}


async def _webhook_rate_limit(request: Request) -> None:
    try:
        await enforce_rate_limit(
            request,
            action="razorpay-webhook",
            limit=request.app.state.settings.webhook_rate_limit_per_minute,
        )
    except RedisError as exc:
        logger.error("razorpay_webhook_rate_limit_unavailable")
        raise HTTPException(status_code=503, detail="Webhook processing is temporarily unavailable.") from exc


async def _read_body(request: Request, limit: int) -> bytes:
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="Webhook payload is too large.")
        data.extend(chunk)
    return bytes(data)


def _webhook_entity(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
    wrapper = payload.get(key)
    if not isinstance(wrapper, dict):
        return None
    entity = wrapper.get("entity")
    return entity if isinstance(entity, dict) else None


def _status_from_event(event_type: str, subscription: dict[str, Any]) -> str | None:
    event_status = {
        "subscription.created": "created",
        "subscription.authenticated": "authenticated",
        "subscription.activated": "active",
        "subscription.charged": "active",
        "subscription.pending": "pending",
        "subscription.halted": "halted",
        "subscription.paused": "paused",
        "subscription.resumed": "active",
        "subscription.cancelled": "cancelled",
        "subscription.completed": "completed",
        "subscription.expired": "expired",
    }.get(event_type)
    if event_type == "subscription.updated":
        event_status = subscription.get("status")
    if event_status not in PROVIDER_SUBSCRIPTION_STATUSES:
        return None
    return event_status


async def _record_payment(
    session: AsyncSession,
    *,
    organization_id: UUID,
    subscription: Subscription,
    payment: dict[str, Any],
    start_at: Any,
    end_at: Any,
    provider_event_at: datetime | None,
) -> None:
    payment_id = payment.get("id")
    amount = payment.get("amount")
    currency = payment.get("currency")
    if (
        not isinstance(payment_id, str)
        or not isinstance(amount, int)
        or amount < 0
        or not isinstance(currency, str)
        or len(currency) != 3
    ):
        return
    if payment.get("subscription_id") not in {None, subscription.razorpay_subscription_id}:
        return
    existing = await session.scalar(
        select(Payment).where(
            Payment.organization_id == organization_id,
            Payment.razorpay_payment_id == payment_id,
        )
    )
    if existing is not None:
        existing_event_time = existing.provider_event_at
        if existing_event_time is not None and existing_event_time.tzinfo is None:
            existing_event_time = existing_event_time.replace(tzinfo=UTC)
        if (
            existing_event_time is None
            or (
                provider_event_at is not None
                and provider_event_at > existing_event_time
            )
        ):
            existing.status = str(payment.get("status", existing.status))[:40]
            existing.provider_event_at = provider_event_at
        return
    session.add(
        Payment(
            organization_id=organization_id,
            subscription_id=subscription.id,
            razorpay_payment_id=payment_id,
            amount=Decimal(amount) / Decimal(100),
            currency=currency,
            status=str(payment.get("status", "unknown"))[:40],
            provider_event_at=provider_event_at,
            billing_period_start_at=_provider_time(start_at),
            billing_period_end_at=_provider_time(end_at),
        )
    )
