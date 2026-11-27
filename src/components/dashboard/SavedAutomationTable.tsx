import { useMemo, useState } from 'react'
import { ArrowUpRight, CalendarDays, Pencil, Search, Settings2, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Automation, AutomationStatus } from '../../types'

type Props = {
  automations: Automation[]
  compact?: boolean
  search?: string
  onDelete?: (automation: Automation) => void
  onStatusChange?: (automation: Automation, status: 'Active' | 'Paused') => void
}

export function SavedAutomationTable({ automations, compact = false, search = '', onDelete, onStatusChange }: Props) {
  const [queryState, setQueryState] = useState({ source: search, value: search })
  const query = queryState.source === search ? queryState.value : search
  const [platform, setPlatform] = useState('')
  const [status, setStatus] = useState('')
  const filtered = useMemo(() => automations.filter((automation) => {
    const matchesQuery = `${automation.name} ${automation.platform} ${automation.accountName} ${automation.contentType} ${automation.postUrl}`.toLowerCase().includes(query.toLowerCase())
    return matchesQuery && (!platform || automation.platform === platform) && (!status || automation.status === status)
  }), [automations, platform, query, status])
  const rows = compact ? filtered.slice(0, 4) : filtered

  return <section className={`dashboard-panel saved-automations-panel${compact ? ' compact' : ''}`}>
    <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">YOUR WORKFLOWS</span><h2>{compact ? 'Recent Automations' : 'My Automations'}</h2><p>{compact ? 'Organization automations and confirmed execution totals.' : 'Search, filter, and manage backend-saved automations.'}</p></div><Link className="saved-automation-create" to="/dashboard/automations/create">+ Create New</Link></div>
    {!compact && <div className="saved-automation-filters"><label className="saved-automation-search"><Search size={15} /><input value={query} onChange={(event) => setQueryState({ source: search, value: event.target.value })} placeholder="Search automations…" aria-label="Search automations" /></label><select value={platform} onChange={(event) => setPlatform(event.target.value)} aria-label="Filter by platform"><option value="">All platforms</option><option value="Instagram">Instagram</option><option value="Facebook">Facebook</option></select><select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status"><option value="">All statuses</option><option value="Draft">Draft</option><option value="Needs setup">Needs setup</option><option value="Active">Active</option><option value="Paused">Paused</option></select></div>}
    {rows.length ? <div className="dashboard-table-scroll"><table className="dashboard-data-table saved-automation-table"><thead><tr><th>Automation Name</th><th>Platform</th><th>Social Account</th><th>Content Type</th><th>Reel / Post URL</th><th>Status</th><th>Keywords</th><th>Matching Method</th><th>Public Reply</th><th>Executions</th><th>Sent</th><th>Failed</th><th>Configuration</th><th>Created</th><th>Actions</th></tr></thead><tbody>{rows.map((automation) => <AutomationRow key={automation.id} automation={automation} onDelete={onDelete} onStatusChange={onStatusChange} />)}</tbody></table></div> : <div className="saved-automation-empty"><span className="saved-automation-empty-icon"><CalendarDays size={18} /></span><strong>{query || platform || status ? 'No matching automations' : 'No automations yet'}</strong><p>{query || platform || status ? 'Try adjusting your search or filters.' : 'Create an automation to configure your first Meta workflow.'}</p>{!compact && !query && !platform && !status && <Link className="btn btn-primary" to="/dashboard/automations/create">Create New Automation</Link>}</div>}
    {!compact && rows.length > 0 && <p className="saved-automation-footnote">Automation runs require configured Meta webhook subscriptions and granted permissions.</p>}
  </section>
}

function AutomationRow({ automation, onDelete, onStatusChange }: { automation: Automation; onDelete?: (automation: Automation) => void; onStatusChange?: (automation: Automation, status: 'Active' | 'Paused') => void }) {
  const status = automation.status as AutomationStatus
  const configured = Boolean(automation.commentTrigger?.keywords.length && (automation.privateReplyText || automation.commentTrigger.publicReplyEnabled))
  let safePostUrl: string | null = null
  try {
    const url = new URL(automation.postUrl)
    if (url.protocol === 'https:') safePostUrl = url.href
  } catch {
    safePostUrl = null
  }
  return <tr>
    <td><Link className="saved-automation-name" to={`/dashboard/automations/${encodeURIComponent(automation.id)}`}>{automation.name}</Link></td>
    <td><span className={`platform-label ${automation.platform.toLowerCase()}`}>{automation.platform}</span></td>
    <td>{automation.accountName}</td>
    <td>{automation.contentType}</td>
    <td>{safePostUrl ? <a className="saved-automation-url" href={safePostUrl} target="_blank" rel="noreferrer" title={safePostUrl}>{safePostUrl}</a> : <span className="saved-automation-url">Invalid URL</span>}</td>
    <td><span className={`automation-status-pill ${status.toLowerCase().replace(/\s+/g, '-')}`}>{status}</span></td>
    <td><span className="automation-table-keywords">{automation.commentTrigger?.keywords.length ? automation.commentTrigger.keywords.join(', ') : 'Not set'}</span></td>
    <td>{automation.commentTrigger?.matchingMethod === 'exact' ? 'Exact' : automation.commentTrigger?.matchingMethod === 'contains' ? 'Contains' : automation.commentTrigger ? 'Any phrase' : 'Not set'}</td>
    <td><span className={`automation-status-pill ${automation.commentTrigger?.publicReplyEnabled ? 'active' : ''}`}>{automation.commentTrigger?.publicReplyEnabled ? 'Enabled' : 'Disabled'}</span></td>
    <td>{automation.executions ?? 0}</td>
    <td>{automation.sentMessages ?? 0}</td>
    <td>{automation.failedMessages ?? 0}</td>
    <td><Link className={`automation-status-pill ${configured ? 'active' : 'needs-setup'}`} to={`/dashboard/automations/configure?id=${encodeURIComponent(automation.id)}`}>{configured ? 'Configured' : 'Not configured'}</Link></td>
    <td>{new Date(automation.createdAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</td>
    <td><div className="saved-automation-actions"><Link to={`/dashboard/automations/${encodeURIComponent(automation.id)}`} aria-label={`View ${automation.name}`} title="View"><ArrowUpRight size={14} /></Link><Link to={`/dashboard/automations/configure?id=${encodeURIComponent(automation.id)}`} aria-label={`Configure triggers for ${automation.name}`} title="Configure triggers"><Settings2 size={14} /></Link><Link to={`/dashboard/automations/create?edit=${encodeURIComponent(automation.id)}`} aria-label={`Edit ${automation.name}`} title="Edit"><Pencil size={14} /></Link>{onStatusChange && automation.status !== 'Needs setup' && <button type="button" onClick={() => onStatusChange(automation, automation.status === 'Active' ? 'Paused' : 'Active')} aria-label={`${automation.status === 'Active' ? 'Pause' : 'Activate'} ${automation.name}`}>{automation.status === 'Active' ? 'Pause' : 'Activate'}</button>}{onDelete && <button type="button" onClick={() => onDelete(automation)} aria-label={`Delete ${automation.name}`} title="Delete"><Trash2 size={14} /></button>}</div></td>
  </tr>
}
