from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BillingPlanResponse(BaseModel):
    name: str = "DM Karo Monthly"
    amount: Decimal = Decimal("299.00")
    currency: str = "INR"
    interval: Literal["monthly"] = "monthly"
    fair_usage_notice: str = "Fair usage and third-party API limits apply."


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_name: str
    amount: Decimal
    currency: str
    status: str
    billing_start_at: datetime | None
    billing_end_at: datetime | None
    next_billing_at: datetime | None
    grace_period_ends_at: datetime | None
    cancel_at_cycle_end: bool
    cancellation_requested_at: datetime | None


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    amount: Decimal
    currency: str
    status: str
    billing_period_start_at: datetime | None
    billing_period_end_at: datetime | None
    created_at: datetime


class BillingOverviewResponse(BaseModel):
    plan: BillingPlanResponse
    subscription: SubscriptionResponse | None
    payments: list[PaymentResponse] = Field(default_factory=list)


class CheckoutResponse(BaseModel):
    key_id: str
    subscription_id: str
    checkout_url: str | None
    status: str
    plan: BillingPlanResponse


class CheckoutVerificationRequest(BaseModel):
    razorpay_payment_id: str = Field(pattern=r"^pay_[A-Za-z0-9]{14}$")
    razorpay_subscription_id: str = Field(pattern=r"^sub_[A-Za-z0-9]{14}$")
    razorpay_signature: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")


class CheckoutVerificationResponse(BaseModel):
    verified: bool
    payment_status: str
    subscription_status: str
    message: str


class CancellationRequest(BaseModel):
    cancel_at_cycle_end: bool = True


class CancellationResponse(BaseModel):
    status: str
    cancel_at_cycle_end: bool
    message: str
