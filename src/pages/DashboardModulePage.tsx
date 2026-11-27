import { ArrowRight, Construction, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useOutletContext } from 'react-router-dom'
import { AutomationTable } from '../components/dashboard/AutomationTable'
import { SocialAccountSelector } from '../components/dashboard/SocialAccountSelector'
import { demoAutomations, demoActivity, moduleCopy } from '../data/dashboardDemoData'
import type { DashboardContext } from './DashboardOverviewPage'

const moduleByPath: Record<string, keyof typeof moduleCopy> = {
  automations: 'automations', 'automations/create': 'create', comments: 'comments',
  messages: 'messages', inbox: 'inbox', leads: 'leads', analytics: 'analytics', 'ai-assistant': 'ai',
  media: 'media', settings: 'settings', support: 'support',
}

const demoRecords: Record<string, string[]> = {
  comments: ['@sarah.creates · “Can you share the details?” · Instagram · 8 min ago', '@jordan.makes · “INFO please” · Instagram · 22 min ago', '@studio.ella · “Is this available?” · Facebook · 35 min ago'],
  messages: ['Welcome DM sent · Instagram · 2 min ago', 'Product guide sent · Facebook · 26 min ago', 'Reply delivered · Instagram · 41 min ago'],
  inbox: ['Sarah C. · Thanks, that’s exactly what I needed! · Instagram', 'Jordan M. · Could you send me the guide? · Facebook', 'Ella S. · Is this available in another color? · Instagram'],
  leads: ['Sarah C. · Instagram · Interested · Today', 'Jordan M. · Facebook · Requested guide · Today', 'Ella S. · Instagram · Product inquiry · Today'],
  analytics: ['Comments received · 2,481 · +18.6%', 'Automated DMs sent · 1,936 · +12.4%', 'Successful replies · 94.8% · Demo metric'],
  ai: ['Suggested reply · “Thanks for your interest! Here are the details…”', 'Tone preset · Friendly and helpful · Preview only'],
  media: ['Summer collection Reel · Instagram preview', 'Product guide image · Demo asset', 'New arrivals post · Facebook preview'],
  settings: ['Workspace profile · Demo workspace', 'Notifications · Preview settings', 'Account security · No real login configured'],
  support: ['Getting started with automations · Guide preview', 'Connecting a social account · Available in a future phase'],
}

export function DashboardModulePage() {
  const location = useLocation()
  const { search } = useOutletContext<DashboardContext>()
  const [selectedAccount, setSelectedAccount] = useState('')
  const key = location.pathname.replace('/dashboard/', '')
  const moduleKey = moduleByPath[key] ?? 'automations'
  const content = moduleCopy[moduleKey]
  const platform = new URLSearchParams(location.search).get('platform')
  const moduleTitle = moduleKey === 'comments' && platform ? `${platform === 'instagram' ? 'Instagram' : 'Facebook'} Comments` : content.title
  const selectedAutomations = demoAutomations
  const records = demoRecords[moduleKey] ?? []
  const filteredRecords = records.filter((record) => record.toLowerCase().includes(search.toLowerCase()) && (!platform || record.toLowerCase().includes(platform)))

  return <div className="dashboard-page-content module-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">DM KARO WORKSPACE · DEMO</span><h1>{moduleTitle}</h1><p>{content.description}</p></div><span className="dashboard-date-chip"><i /> DEMO PREVIEW</span></div>
    {moduleKey === 'automations' && <AutomationTable automations={selectedAutomations} search={search} />}
    {moduleKey === 'create' ? <section className="module-placeholder-card"><span className="module-placeholder-icon"><Sparkles /></span><h2>Build your first workflow</h2><p>Automation setup will be available in a later phase. For now, explore the demo workflows and dashboard analytics.</p><div className="module-account-selector"><SocialAccountSelector value={selectedAccount} onChange={setSelectedAccount} label="Choose a channel account" /></div>{!selectedAccount && <Link className="module-connect-account-link" to="/dashboard/accounts">Connect Meta accounts <ArrowRight size={13} /></Link>}<Link className="btn btn-primary" to="/dashboard/automations">Explore demo automations <ArrowRight size={15} /></Link></section> : null}
    {!['automations', 'create'].includes(moduleKey) && <section className="dashboard-panel module-records-panel"><div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">{platform ? `${platform.toUpperCase()} · ` : ''}SAMPLE RECORDS</span><h2>{moduleTitle} preview</h2><p>All content is simulated demo data and is not connected to a live account.</p></div><span className="dashboard-demo-pill-small">DEMO DATA</span></div><div className="module-record-list">{filteredRecords.length ? filteredRecords.map((record) => <article key={record}><span className="module-record-icon"><Construction size={16} /></span><span>{record}</span><i>DEMO</i></article>) : <p className="dashboard-empty-state">No demo records match your search.</p>}</div></section>}
    {moduleKey === 'analytics' && <p className="module-note">Sample metrics only. <Link to="/dashboard">Return to dashboard analytics overview.</Link></p>}
    <span className="module-activity-hint">Recent demo activity: {demoActivity[0].title.toLowerCase()}.</span>
  </div>
}
