import { useState } from 'react'
import { ArrowUpRight, MoreHorizontal } from 'lucide-react'
import type { DemoAutomation } from '../../types'
import { Link } from 'react-router-dom'

export function AutomationTable({ automations, search = '', compact = false }: { automations: DemoAutomation[]; search?: string; compact?: boolean }) {
  const [statusFilter, setStatusFilter] = useState<'All' | 'Active' | 'Paused'>('All')
  const filtered = automations.filter((automation) => {
    const matchesStatus = statusFilter === 'All' || automation.status === statusFilter
    const searchable = `${automation.name} ${automation.platform} ${automation.content} ${automation.keywords.join(' ')}`.toLowerCase()
    return matchesStatus && searchable.includes(search.toLowerCase())
  })

  return <section className={`dashboard-panel automation-panel${compact ? ' compact' : ''}`}>
    <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">WORKFLOWS · DEMO DATA</span><h2>{compact ? 'Recent Automations' : 'My Automations'}</h2><p>Sample workflows only. No social accounts are connected.</p></div><div className="dashboard-panel-actions"><select aria-label="Filter automations by status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'All' | 'Active' | 'Paused')}><option>All</option><option>Active</option><option>Paused</option></select><Link to="/dashboard/automations" className="dashboard-text-link">{compact ? 'View all' : 'Manage automations'} <ArrowUpRight size={14} /></Link></div></div>
    <div className="dashboard-table-scroll"><table className="dashboard-table"><thead><tr><th>Automation Name</th><th>Platform</th><th>Reel / Post</th><th>Keywords</th><th>Comments</th><th>DMs Sent</th><th>Status</th><th aria-label="Actions"></th></tr></thead><tbody>
      {filtered.length ? filtered.map((automation) => <tr key={automation.id}><td><strong className="automation-name">{automation.name}</strong><span className="automation-row-demo">DEMO WORKFLOW</span></td><td><span className={`platform-label ${automation.platform.toLowerCase()}`}><i />{automation.platform}</span></td><td>{automation.content}</td><td><span className="automation-keywords">{automation.keywords.map((keyword) => <i key={keyword}>{keyword}</i>)}</span></td><td>{automation.comments}</td><td>{automation.messages}</td><td><span className={`automation-status ${automation.status.toLowerCase()}`}><i />{automation.status}</span></td><td><button className="automation-row-menu" type="button" aria-label={`More actions for ${automation.name}`}><MoreHorizontal size={18} /></button></td></tr>) : <tr><td className="dashboard-table-empty" colSpan={8}>No demo automations match this search and filter.</td></tr>}
    </tbody></table></div>
  </section>
}
