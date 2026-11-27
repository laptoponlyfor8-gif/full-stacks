import { useEffect, useState } from 'react'
import { Link, useLocation, useOutletContext } from 'react-router-dom'
import { AlertCircle, Plus } from 'lucide-react'
import { SavedAutomationTable } from '../components/dashboard/SavedAutomationTable'
import { changeAutomationStatus, listAutomations, removeAutomation } from '../services/automationsApi'
import type { Automation } from '../types'
import type { DashboardContext } from './DashboardOverviewPage'

export function AutomationsPage() {
  const { search } = useOutletContext<DashboardContext>()
  const location = useLocation()
  const [automations, setAutomations] = useState<Automation[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState((location.state as { notice?: string } | null)?.notice ?? '')

  useEffect(() => {
    let active = true
    listAutomations()
      .then((items) => { if (active) setAutomations(items) })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : 'Could not load automations.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const handleDelete = async (automation: Automation) => {
    if (!window.confirm(`Delete "${automation.name}"? This cannot be undone.`)) return
    try {
      await removeAutomation(automation.id)
      setAutomations((current) => current.filter((item) => item.id !== automation.id))
      setNotice('Automation deleted.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete the automation.')
    }
  }

  const handleStatusChange = async (automation: Automation, status: 'Active' | 'Paused') => {
    try {
      const updated = await changeAutomationStatus(automation.id, status)
      setAutomations((current) => current.map((item) => item.id === updated.id ? updated : item))
      setNotice(status === 'Active' ? 'Automation activated.' : 'Automation paused.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update the automation.')
    }
  }

  return <div className="dashboard-page-content automations-list-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">WORKSPACE · AUTOMATIONS</span><h1>My Automations</h1><p>Manage your organization’s Meta-connected automation workflows.</p></div><Link className="btn btn-primary" to="/dashboard/automations/create"><Plus size={15} /> Create New Automation</Link></div>
    <div className="automation-demo-notice"><span><strong>Meta delivery depends on account eligibility and approved permissions.</strong><small>Only backend-confirmed message responses are counted as sent. Unsupported or restricted events are not delivered.</small></span></div>
    {notice && <div className="automation-feedback success" role="status">{notice}</div>}
    {error && <div className="automation-feedback error" role="alert"><AlertCircle size={15} />{error}</div>}
    {loading ? <p role="status">Loading automations…</p> : <SavedAutomationTable automations={automations} search={search} onDelete={handleDelete} onStatusChange={handleStatusChange} />}
  </div>
}
