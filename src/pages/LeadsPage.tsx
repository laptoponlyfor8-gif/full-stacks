import { useEffect, useRef, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { addContactNote, listContactNotes, listLeadActivities, listLeads, updateLeadStatus } from '../services/crmApi'
import type { Contact, ContactNote, LeadStatus } from '../services/crmApi'
import type { DashboardContext } from './DashboardOverviewPage'
import '../crm.css'

const leadStatuses: LeadStatus[] = ['new', 'interested', 'qualified', 'converted', 'lost']
const pageSize = 25

export function LeadsPage() {
  const { search } = useOutletContext<DashboardContext>()
  const { user } = useAuth()
  const canWrite = user?.organization.role === 'owner' || user?.organization.role === 'admin'
  const [leads, setLeads] = useState<Contact[]>([])
  const [selected, setSelected] = useState<Contact | null>(null)
  const [activities, setActivities] = useState<Array<{ id: string; activity_type: string; detail: string; created_at: string }>>([])
  const [notes, setNotes] = useState<ContactNote[]>([])
  const [noteText, setNoteText] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [loadedQuery, setLoadedQuery] = useState('')
  const [error, setError] = useState('')
  const selectedIdRef = useRef('')
  const queryKey = `${search}:${statusFilter}:${offset}`
  const loading = loadedQuery !== queryKey

  useEffect(() => {
    let active = true
    const key = `${search}:${statusFilter}:${offset}`
    listLeads({
      q: search || undefined,
      lead_status: statusFilter ? statusFilter as LeadStatus : undefined,
      offset,
      limit: pageSize,
    }).then((result) => {
      if (!active) return
      if (offset > 0 && offset >= result.total) {
        setOffset(0)
        return
      }
      setLeads(result.items)
      setTotal(result.total)
      if (selectedIdRef.current && !result.items.some((item) => item.id === selectedIdRef.current)) {
        selectedIdRef.current = ''
        setSelected(null)
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Leads could not be loaded.')
    }).finally(() => { if (active) setLoadedQuery(key) })
    return () => { active = false }
  }, [search, statusFilter, offset])

  const selectLead = async (lead: Contact) => {
    selectedIdRef.current = lead.id
    setSelected(lead)
    setError('')
    try {
      const [activityItems, noteItems] = await Promise.all([
        listLeadActivities(lead.id),
        listContactNotes(lead.id),
      ])
      setActivities(activityItems)
      setNotes(noteItems)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Lead activity could not be loaded.')
    }
  }

  const changeStatus = async (contact: Contact, value: string) => {
    try {
      const updated = await updateLeadStatus(contact.id, value as LeadStatus)
      setLeads((items) => items.map((item) => item.id === updated.id ? updated : item))
      setSelected((current) => current?.id === updated.id ? updated : current)
      setActivities(await listLeadActivities(contact.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Lead status could not be updated.')
    }
  }

  const submitNote = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!selected || !noteText.trim()) return
    try {
      const note = await addContactNote(selected.id, noteText)
      setNotes((items) => [note, ...items])
      setNoteText('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Lead note could not be saved.')
    }
  }

  return <div className="dashboard-page-content crm-page">
    <div className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">WORKSPACE · CRM</span><h1>Leads</h1><p>Track real contacts and the current status your team assigned.</p></div>
      <span className="dashboard-date-chip"><i /> {total} RECORDS</span>
    </div>
    <div className="crm-toolbar">
      <label>Status filter<select value={statusFilter} onChange={(event) => { setOffset(0); setStatusFilter(event.target.value) }}><option value="">All statuses</option>{leadStatuses.map((status) => <option value={status} key={status}>{status}</option>)}</select></label>
      <span className="crm-muted">Use the dashboard search to find a contact.</span>
    </div>
    {error && <p className="crm-feedback error" role="alert">{error}</p>}
    <div className="crm-inbox-grid">
      <section className="crm-card" style={{ gridColumn: selected ? '1 / 3' : '1 / -1' }}>
        <div className="crm-card-head"><div><h2>Lead records</h2><p>{total} contacts</p></div></div>
        <div className="crm-table-wrap"><table className="crm-table"><thead><tr><th>Contact</th><th>Source</th><th>Status</th><th>Last interaction</th></tr></thead>
          <tbody>{loading ? <tr><td colSpan={4}>Loading leads…</td></tr> : leads.length === 0 ? <tr><td colSpan={4}>No lead records match this filter.</td></tr> : leads.map((lead) => <tr key={lead.id} aria-selected={selected?.id === lead.id} onClick={() => void selectLead(lead)}>
            <td><span className="crm-name">{lead.display_name || lead.platform_customer_id}</span><br /><span className="crm-muted">{lead.platform_customer_id}</span></td>
            <td><span className="crm-platform">{lead.platform}</span></td>
            <td><span className="crm-status">{lead.lead_status}</span></td>
            <td>{lead.last_interaction_at ? new Date(lead.last_interaction_at).toLocaleDateString() : '—'}</td>
          </tr>)}</tbody>
        </table></div>
        <div className="crm-pagination"><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} of ${total}` : '0 leads'}</span><span><button className="crm-button ghost" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button> <button className="crm-button ghost" type="button" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next</button></span></div>
      </section>
      {selected && <aside className="crm-card crm-profile">
        <div className="crm-card-head"><div><h2>{selected.display_name || selected.platform_customer_id}</h2><p>{selected.platform} · Lead activity</p></div><button className="crm-button ghost" type="button" onClick={() => { selectedIdRef.current = ''; setSelected(null) }}>Close</button></div>
        <div className="crm-profile-body">
          <label className="crm-profile-field">Lead status<select value={selected.lead_status} disabled={!canWrite} onChange={(event) => void changeStatus(selected, event.target.value)}>{leadStatuses.map((status) => <option value={status} key={status}>{status}</option>)}</select></label>
          <div className="crm-profile-field">First contact<strong>{selected.first_contact_at ? new Date(selected.first_contact_at).toLocaleString() : 'Not available'}</strong></div>
          <div className="crm-profile-field">Last interaction<strong>{selected.last_interaction_at ? new Date(selected.last_interaction_at).toLocaleString() : 'Not available'}</strong></div>
          <Link className="crm-button secondary" to={`/dashboard/inbox?contact=${encodeURIComponent(selected.id)}`}>Open conversation</Link>
          <div><h3>Lead activity</h3><div className="crm-note-list">{activities.length ? activities.map((activity) => <article className="crm-note" key={activity.id}>{activity.detail}<small className="crm-muted"> · {new Date(activity.created_at).toLocaleString()}</small></article>) : <p className="crm-muted">No recorded lead status activity.</p>}</div></div>
          <div><h3>Private notes</h3><div className="crm-note-list">{notes.map((note) => <article className="crm-note" key={note.id}>{note.content}<small className="crm-muted"> · {new Date(note.created_at).toLocaleString()}</small></article>)}</div></div>
          <form className="crm-note-form" onSubmit={(event) => void submitNote(event)}><label htmlFor="lead-note">Add a private note</label><textarea id="lead-note" value={noteText} onChange={(event) => setNoteText(event.target.value)} maxLength={5000} /><button className="crm-button secondary" type="submit" disabled={!noteText.trim()}>Save note</button></form>
        </div>
      </aside>}
    </div>
  </div>
}
