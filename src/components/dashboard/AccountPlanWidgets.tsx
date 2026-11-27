import { ArrowUpRight, Camera, Check, MessageCircle, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ConnectionStatusBadge } from './ConnectionStatusBadge'
import { useSocialAccounts } from '../../hooks/useSocialAccounts'
import type { SocialPlatform } from '../../types'

export function ConnectedAccountsWidget() {
  const { accounts } = useSocialAccounts()
  const connectedCount = accounts.filter((account) => account.is_connected && account.connection_status === 'connected').length

  return <section className="dashboard-panel accounts-widget">
    <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">CHANNELS · {connectedCount} CONNECTED</span><h2>Connected Accounts</h2></div><Link to="/dashboard/accounts" aria-label="Manage connected accounts"><ArrowUpRight size={16} /></Link></div>
    <div className="account-demo-notice"><span>META OAUTH</span> Connection status is loaded from the backend for your organization.</div>
    {(['instagram', 'facebook'] as SocialPlatform[]).map((platform) => {
      const account = accounts.find((item) => item.platform === platform && item.connection_status === 'connected')
        ?? accounts.find((item) => item.platform === platform)
      const Icon = platform === 'instagram' ? Camera : MessageCircle
      const badgeStatus = !account ? 'Not Connected' : account.connection_status === 'connected' ? 'Connected' : account.connection_status === 'expired' ? 'Authorization Expired' : 'Disconnected'
      return <article className="connected-account-card" key={platform}><Link className={`connected-account-icon ${platform}`} to={`/dashboard/accounts/${platform}`} aria-label={`Open ${platform} connection page`}><Icon size={18} /></Link><span className="connected-account-copy"><strong>{account?.account_name ?? (platform === 'instagram' ? 'Instagram' : 'Facebook')}</strong><small>{account ? (platform === 'instagram' ? 'Instagram Professional' : 'Facebook Page') : 'Not connected'}</small></span><ConnectionStatusBadge status={badgeStatus} /></article>
    })}
    <Link className="dashboard-widget-action" to="/dashboard/accounts">Manage accounts <ArrowUpRight size={14} /></Link>
  </section>
}

const planFeatures = [
  'All available product features',
  'Instagram automation',
  'Facebook automation',
  'AI assistant',
  'Keyword automation',
  'Lead management',
  'Analytics',
  'Unified inbox · fair usage applies',
]

export function AccountPlanWidget() {
  return <section className="dashboard-plan-widget"><span className="plan-widget-glow" /><div className="plan-widget-top"><span className="plan-widget-icon"><Sparkles size={17} /></span><span className="plan-widget-tag">ALL ACCESS</span></div><span className="plan-widget-label">MONTHLY PLAN</span><h2>DM Karo Monthly</h2><div className="plan-widget-price">₹299 <span>/ month</span></div><div className="plan-widget-status">Open Billing to view current subscription status</div><ul>{planFeatures.map((feature) => <li key={feature}><Check size={14} />{feature}</li>)}</ul><Link to="/dashboard/billing">Manage Billing <ArrowUpRight size={14} /></Link><span className="plan-widget-footnote"><Camera size={12} /> Fair usage and third-party API limits apply.</span></section>
}
