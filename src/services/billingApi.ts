import { authenticatedFetch } from './authApi'

export type BillingPlan = {
  name: string
  amount: string
  currency: string
  interval: 'monthly'
  fair_usage_notice: string
}

export type BillingPayment = {
  id: string
  amount: string
  currency: string
  status: string
  billing_period_start_at: string | null
  billing_period_end_at: string | null
  created_at: string
}

export type BillingSubscription = {
  id: string
  plan_name: string
  amount: string
  currency: string
  status: string
  billing_start_at: string | null
  billing_end_at: string | null
  next_billing_at: string | null
  grace_period_ends_at: string | null
  cancel_at_cycle_end: boolean
  cancellation_requested_at: string | null
}

export type BillingOverview = {
  plan: BillingPlan
  subscription: BillingSubscription | null
  payments: BillingPayment[]
}

export type CheckoutSession = {
  key_id: string
  subscription_id: string
  checkout_url: string | null
  status: string
  plan: BillingPlan
}

export type CheckoutVerification = {
  verified: boolean
  payment_status: string
  subscription_status: string
  message: string
}

export type RazorpayCheckoutResult = {
  razorpay_payment_id: string
  razorpay_subscription_id: string
  razorpay_signature: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`/billing${path}`, {
    ...init,
    headers: new Headers({
      'Content-Type': 'application/json',
      ...Object.fromEntries(new Headers(init?.headers).entries()),
    }),
  })
  const data = await response.json().catch(() => ({})) as { detail?: string } & T
  if (!response.ok) {
    throw new Error(data.detail || 'The billing request could not be completed.')
  }
  return data
}

export function getBillingOverview(): Promise<BillingOverview> {
  return request<BillingOverview>('')
}

export function createBillingSubscription(): Promise<CheckoutSession> {
  return request<CheckoutSession>('/subscriptions', { method: 'POST', body: '{}' })
}

export function verifyBillingCheckout(
  result: RazorpayCheckoutResult,
): Promise<CheckoutVerification> {
  return request<CheckoutVerification>('/checkout/verify', {
    method: 'POST',
    body: JSON.stringify(result),
  })
}

export function cancelBillingSubscription(
  subscriptionId: string,
  cancelAtCycleEnd = true,
): Promise<{ status: string; cancel_at_cycle_end: boolean; message: string }> {
  return request(`/subscriptions/${encodeURIComponent(subscriptionId)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ cancel_at_cycle_end: cancelAtCycleEnd }),
  })
}
