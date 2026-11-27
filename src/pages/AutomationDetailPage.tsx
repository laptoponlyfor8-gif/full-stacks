import { useEffect, useState } from 'react'
import { ArrowLeft, CalendarDays, Pencil, Settings2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { AutomationSummaryCard } from '../components/dashboard/AutomationSummaryCard'
import { changeAutomationStatus, getAutomation } from '../services/automationsApi'
import type { Automation } from '../types'
import type { AutomationFields } from '../utils/automationValidation'

export function AutomationDetailPage() {
  const { id = '' } = useParams()
  const [automation, setAutomation] = useState<Automation | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    getAutomation(id)
      .then((record) => { if (active) setAutomation(record) })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load this automation.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [id])

  const toggleStatus = async () => {
    if (!automation) return
    setSaving(true)
    setError('')
    try {
      setAutomation(await changeAutomationStatus(automation.id, automation.status === 'Active' ? 'Paused' : 'Active'))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update this automation.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="dashboard-page-content" role="status">Loading automation…</div>
  if (error && !automation) return <div className="dashboard-page-content"><div className="automation-feedback error" role="alert">{error}</div><Link to="/dashboard/automations" className="social-back-link"><ArrowLeft size={14} /> Back to My Automations</Link></div>
  if (!automation) return <div className="dashboard-page-content"><div className="automation-feedback error" role="alert">Automation not found.</div><Link to="/dashboard/automations" className="social-back-link"><ArrowLeft size={14} /> Back to My Automations</Link></div>

  const fields: AutomationFields = { name: automation.name, platform: automation.platform, accountId: automation.accountId, contentType: automation.contentType, postUrl: automation.postUrl }
  return <div className="dashboard-page-content automation-detail-page">
    <Link to="/dashboard/automations" className="social-back-link"><ArrowLeft size={14} /> Back to My Automations</Link>
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">AUTOMATION · {automation.status.toUpperCase()}</span><h1>{automation.name}</h1><p>Review the organization-scoped automation and its latest execution totals.</p></div><div className="automation-detail-actions"><Link className="automation-save-draft" to={`/dashboard/automations/configure?id=${encodeURIComponent(automation.id)}`}><Settings2 size={14} /> Configure</Link><Link className="btn btn-primary" to={`/dashboard/automations/create?edit=${encodeURIComponent(automation.id)}`}><Pencil size={14} /> Edit</Link><button className="automation-save-draft" type="button" disabled={saving} onClick={() => void toggleStatus()}>{saving ? 'Saving…' : automation.status === 'Active' ? 'Pause' : 'Activate'}</button></div></div>
    {error && <div className="automation-feedback error" role="alert">{error}</div>}
    <AutomationSummaryCard fields={fields} accountName={automation.accountName} />
    <section className="dashboard-panel detail-trigger-summary"><div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">COMMENT TRIGGERS</span><h2>Keyword configuration</h2><p>{automation.commentTrigger?.matchingMethod === 'exact' ? 'Exact match' : automation.commentTrigger?.matchingMethod === 'contains' ? 'Contains' : 'Phrase match'}</p></div><Link className="automation-summary-edit-link" to={`/dashboard/automations/configure?id=${encodeURIComponent(automation.id)}`}>Edit configuration</Link></div><div className="detail-trigger-keywords">{automation.commentTrigger?.keywords.map((keyword) => <span className="keyword-tag-readonly" key={keyword}>{keyword}</span>)}</div><div className="detail-trigger-meta"><span>Private reply: {automation.privateReplyText ? 'configured' : 'not configured'}</span><span>Public reply: {automation.commentTrigger?.publicReplyEnabled ? 'enabled' : 'disabled'}</span><span>Executions: {automation.executions ?? 0}</span><span>Messages sent: {automation.sentMessages ?? 0}</span><span>Failures: {automation.failedMessages ?? 0}</span></div></section>
    <div className="automation-detail-meta"><span><CalendarDays size={15} /> Created {new Date(automation.createdAt).toLocaleString()}</span><span className={`automation-status-pill ${automation.status.toLowerCase()}`}>{automation.status}</span></div>
  </div>
}
