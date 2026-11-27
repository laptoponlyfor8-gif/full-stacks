import { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, CheckCircle2, CreditCard, LoaderCircle, ShieldCheck, XCircle } from 'lucide-react'
import { useAuth } from '../auth/useAuth'
import {
  cancelBillingSubscription,
  createBillingSubscription,
  getBillingOverview,
  verifyBillingCheckout,
  type BillingOverview,
  type RazorpayCheckoutResult,
} from '../services/billingApi'
import '../billing.css'

type CheckoutOptions = {
  key: string
  subscription_id: string
  name: string
  description: string
  prefill: { name: string; email: string }
  theme: { color: string }
  modal: { ondismiss: () => void }
  handler: (result: RazorpayCheckoutResult) => void
}

type CheckoutInstance = {
  open: () => void
  on: (event: 'payment.failed', handler: (response: { error?: { description?: string } }) => void) => void
}

declare global {
  interface Window {
    Razorpay?: new (options: CheckoutOptions) => CheckoutInstance
  }
}

const checkoutScriptUrl = 'https://checkout.razorpay.com/v1/checkout.js'
let checkoutScript: Promise<void> | null = null

function loadCheckout(): Promise<void> {
  if (window.Razorpay) return Promise.resolve()
  if (checkoutScript) return checkoutScript
  const loading = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = checkoutScriptUrl
    script.async = true
    script.onload = () => window.Razorpay
      ? resolve()
      : reject(new Error('Razorpay Checkout did not initialize.'))
    script.onerror = () => reject(new Error('Razorpay Checkout could not be loaded.'))
    document.body.appendChild(script)
  })
  const stored = loading.catch((error: unknown) => {
    checkoutScript = null
    throw error
  })
  checkoutScript = stored
  return stored
}

function readableStatus(status: string): string {
  return status.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatDate(value: string | null): string {
  if (!value) return 'Not available yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not available yet' : date.toLocaleDateString()
}

export function BillingPage() {
  const { user } = useAuth()
  const [overview, setOverview] = useState<BillingOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setOverview(await getBillingOverview())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Billing details could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    getBillingOverview()
      .then((result) => { if (active) setOverview(result) })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Billing details could not be loaded.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const subscribe = async () => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const session = await createBillingSubscription()
      await loadCheckout()
      if (!window.Razorpay) throw new Error('Razorpay Checkout is unavailable.')
      const checkout = new window.Razorpay({
        key: session.key_id,
        subscription_id: session.subscription_id,
        name: 'DM Karo',
        description: 'DM Karo Monthly',
        prefill: { name: user?.name ?? '', email: user?.email ?? '' },
        theme: { color: '#315fe8' },
        modal: { ondismiss: () => setBusy(false) },
        handler: (result) => {
          setBusy(true)
          void verifyBillingCheckout(result)
            .then(async (verification) => {
              setNotice(verification.message)
              await refresh()
            })
            .catch((reason: unknown) => {
              setError(reason instanceof Error ? reason.message : 'Payment verification could not be completed.')
            })
            .finally(() => setBusy(false))
        },
      })
      checkout.on('payment.failed', ({ error: paymentError }) => {
        setError(paymentError?.description || 'Payment was not completed. You can try again.')
        setBusy(false)
      })
      checkout.open()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Checkout could not be started.')
      setBusy(false)
      await refresh()
    }
  }

  const cancel = async () => {
    if (!overview?.subscription) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await cancelBillingSubscription(overview.subscription.id)
      setNotice(result.message)
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Cancellation could not be requested.')
    } finally {
      setBusy(false)
    }
  }

  const subscription = overview?.subscription
  const canCancel = subscription && !['cancelled', 'completed', 'expired'].includes(subscription.status)
  const canSubscribe = !subscription || ['cancelled', 'completed', 'expired', 'creation_failed'].includes(subscription.status)

  return <div className="dashboard-page-content billing-page">
    <header className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">ACCOUNT · BILLING</span><h1>Billing & subscription</h1><p>Manage the DM Karo monthly plan for this organization.</p></div>
    </header>

    {error && <div className="billing-alert error" role="alert"><XCircle size={17} />{error}</div>}
    {notice && <div className="billing-alert success" role="status"><CheckCircle2 size={17} />{notice}</div>}

    <section className="billing-layout">
      <article className="billing-plan-card">
        <div className="billing-plan-heading"><span className="billing-plan-icon"><CreditCard size={19} /></span><span className="billing-plan-badge">ONE MONTHLY PLAN</span></div>
        <span className="dashboard-section-kicker">DM KARO MONTHLY</span>
        <h2>All available product features</h2>
        <div className="billing-price">₹299 <span>/ month</span></div>
        <p>Access to current DM Karo features. Fair usage and third-party API restrictions apply.</p>
        <ul>
          <li><CheckCircle2 size={15} /> Instagram and Facebook automation</li>
          <li><CheckCircle2 size={15} /> Unified inbox, contacts and leads</li>
          <li><CheckCircle2 size={15} /> AI assistance and analytics</li>
        </ul>
        <button className="billing-primary-button" type="button" disabled={busy || loading || !canSubscribe} onClick={() => void subscribe()}>
          {busy ? <LoaderCircle size={16} className="billing-spinner" /> : <CreditCard size={16} />}
          {subscription && !canSubscribe ? 'Subscription already in progress' : 'Subscribe · ₹299/month'}
        </button>
        <div className="billing-safe-note"><ShieldCheck size={15} /> Razorpay securely handles payment details. DM Karo never stores card or UPI credentials.</div>
      </article>

      <article className="billing-details-card">
        <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">CURRENT STATUS</span><h2>Subscription details</h2></div></div>
        {loading ? <div className="billing-loading"><LoaderCircle size={18} className="billing-spinner" />Loading billing details…</div>
          : !subscription ? <div className="billing-empty"><CreditCard size={20} /><strong>No subscription yet</strong><span>Choose the monthly plan to begin Razorpay Test Mode checkout.</span></div>
            : <div className="billing-subscription-details">
              <div className="billing-status-row"><span>Status</span><strong className={`billing-status ${subscription.status}`}>{readableStatus(subscription.status)}</strong></div>
              <div className="billing-status-row"><span>Plan</span><strong>{subscription.plan_name}</strong></div>
              <div className="billing-status-row"><span>Price</span><strong>₹{subscription.amount} / month</strong></div>
              <div className="billing-status-row"><span>Next billing date</span><strong>{formatDate(subscription.next_billing_at)}</strong></div>
              <div className="billing-status-row"><span>Current period ends</span><strong>{formatDate(subscription.billing_end_at)}</strong></div>
              {subscription.grace_period_ends_at && <div className="billing-status-row"><span>Grace period ends</span><strong>{formatDate(subscription.grace_period_ends_at)}</strong></div>}
              {['pending', 'halted'].includes(subscription.status) && <p className="billing-cancel-note">{subscription.status === 'pending' ? 'Razorpay is retrying the failed charge. Your workspace data remains available during the grace period.' : 'Razorpay has exhausted its automatic retries. Follow the payment update instructions from Razorpay; workspace data is retained.'}</p>}
              {subscription.cancellation_requested_at && <p className="billing-cancel-note">Cancellation requested. Final status will update when Razorpay confirms it.</p>}
              {canCancel && <button className="billing-cancel-button" type="button" disabled={busy} onClick={() => void cancel()}>Cancel renewal at period end <ArrowUpRight size={14} /></button>}
            </div>}
      </article>
    </section>

    <section className="billing-history-card">
      <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">RAZORPAY RECORDS</span><h2>Payment history</h2></div></div>
      {loading ? <div className="billing-loading">Loading payment history…</div>
        : overview?.payments.length
          ? <div className="billing-history-list">{overview.payments.map((payment) => <div className="billing-payment-row" key={payment.id}><div><strong>₹{payment.amount} {payment.currency}</strong><span>{formatDate(payment.created_at)}</span></div><span className={`billing-status ${payment.status}`}>{readableStatus(payment.status)}</span></div>)}</div>
          : <p className="billing-history-empty">No confirmed payment records are available.</p>}
      <small>Subscription activation and payment records are updated from verified Razorpay responses and webhooks.</small>
    </section>
  </div>
}
