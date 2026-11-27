import { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { AccountPlanWidget, ConnectedAccountsWidget } from '../components/dashboard/AccountPlanWidgets'
import { SavedAutomationTable } from '../components/dashboard/SavedAutomationTable'
import { QuickActions } from '../components/dashboard/QuickActions'
import { StatCard } from '../components/dashboard/StatCard'
import type { Automation } from '../types'
import { listAutomations } from '../services/automationsApi'
import { getAnalytics } from '../services/crmApi'
import type { Analytics } from '../services/crmApi'

export type DashboardContext = { search: string; profile: { fullName: string; businessName: string; email: string; mobile: string } | null; connectedAccountCount: number }

export function DashboardOverviewPage() {
  const { search, profile } = useOutletContext<DashboardContext>()
  const [automations, setAutomations] = useState<Automation[]>([])
  const [automationError, setAutomationError] = useState('')
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [analyticsError, setAnalyticsError] = useState('')
  useEffect(() => {
    let active = true
    listAutomations()
      .then((items) => {
        if (!active) return
        setAutomations(items)
      })
      .catch((error: unknown) => {
        if (active) setAutomationError(error instanceof Error ? error.message : 'Could not load automations.')
      })
    getAnalytics()
      .then((result) => { if (active) setAnalytics(result) })
      .catch((error: unknown) => { if (active) setAnalyticsError(error instanceof Error ? error.message : 'Could not load analytics.') })
    return () => { active = false }
  }, [])
  const metric = (label: string, value: number | undefined, available: boolean, caption: string, icon: string) => ({
    label,
    value: available && value !== undefined ? value.toLocaleString() : '—',
    change: caption,
    trend: 'neutral' as const,
    icon,
    demo: false,
  })
  const stats = analytics ? [
    metric('Connected Accounts', analytics.connected_accounts.value, analytics.connected_accounts.available, 'Current accounts', 'accounts'),
    metric('Active Automations', analytics.active_automations.value, analytics.active_automations.available, 'Current workflows', 'automations'),
    metric('Automation Executions', analytics.automation_executions.value, analytics.automation_executions.available, 'Last 30 days', 'automations'),
    metric('Successful Executions', analytics.successful_executions.value, analytics.successful_executions.available, 'Meta-confirmed', 'success'),
    metric('Failed Executions', analytics.failed_executions.value, analytics.failed_executions.available, 'Last 30 days', 'messages'),
    metric('Messages Sent', analytics.messages_sent.value, analytics.messages_sent.available, 'Last 30 days', 'messages'),
    metric('Messages Received', analytics.messages_received.value, analytics.messages_received.available, 'Webhook records', 'comments'),
    metric('Total Contacts', analytics.total_contacts.value, analytics.total_contacts.available, 'Current CRM records', 'leads'),
    metric('New Leads', analytics.new_leads.value, analytics.new_leads.available, 'Last 30 days', 'leads'),
    metric('Converted Leads', analytics.converted_leads.value, analytics.converted_leads.available, 'Last 30 days', 'leads'),
  ].filter((stat) => stat.label.toLowerCase().includes(search.toLowerCase())) : []

  return <div className="dashboard-page-content">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">OVERVIEW</span><h1>Good morning, {profile?.fullName.split(' ')[0] || 'there'} <span>✦</span></h1><p>Review your connected accounts and automation activity.</p></div><span className="dashboard-date-chip"><i /> ACCOUNT STATUS</span></div>
    <div className="dashboard-demo-banner"><span className="dashboard-demo-banner-icon"><Sparkles size={16} /></span><span><strong>Organization metrics from stored records</strong><small>Message history starts with supported webhooks; historical conversations are not imported automatically.</small></span><Link to="/dashboard/analytics">View analytics</Link></div>
    {analyticsError && <p className="automation-feedback error" role="alert">{analyticsError}</p>}
    <section className="dashboard-stats-grid" aria-label="Organization statistics">{analytics ? stats.length ? stats.map((stat) => <StatCard key={stat.label} {...stat} />) : <p className="dashboard-search-empty">No metrics match “{search}”.</p> : !analyticsError && <p role="status">Loading organization analytics…</p>}</section>
    <QuickActions />
    {automationError ? <p className="automation-feedback error" role="alert">{automationError}</p> : <SavedAutomationTable automations={automations} search={search} compact />}
    <div className="dashboard-widgets-grid"><ConnectedAccountsWidget /><AccountPlanWidget /></div>
  </div>
}
