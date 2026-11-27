import { useEffect, useRef, useState } from 'react'
import { Plus, Save } from 'lucide-react'
import { useOutletContext } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { useSocialAccounts } from '../hooks/useSocialAccounts'
import {
  addContactNote, createContact, createTag, listContactNotes, listContacts, listTags,
  replaceContactTags, updateContact,
} from '../services/crmApi'
import type { Contact, ContactNote, LeadStatus, Platform } from '../services/crmApi'
import type { DashboardContext } from './DashboardOverviewPage'
import '../crm.css'

const pageSize = 25

export function ContactsPage() {
  const { search } = useOutletContext<DashboardContext>()
  const { user } = useAuth()
  const { accounts } = useSocialAccounts()
  const canWrite = user?.organization.role === 'owner' || user?.organization.role === 'admin'
  const availableAccounts = accounts.filter((account) => account.is_connected && account.connection_status === 'connected')
  const [contacts, setContacts] = useState<Contact[]>([])
  const [selected, setSelected] = useState<Contact | null>(null)
  const [notes, setNotes] = useState<ContactNote[]>([])
  const [tags, setTags] = useState<Array<{ id: string; name: string; created_at: string }>>([])
  const [selectedTagIds, setSelectedTagIds] = useState<string[]>([])
  const [offset, setOffset] = useState(0)
  const [platformFilter, setPlatformFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [total, setTotal] = useState(0)
  const [loadedQuery, setLoadedQuery] = useState('')
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [showCreate, setShowCreate] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [customerId, setCustomerId] = useState('')
  const [name, setName] = useState('')
  const [customFieldsText, setCustomFieldsText] = useState('{}')
  const [editName, setEditName] = useState('')
  const [editCustomFieldsText, setEditCustomFieldsText] = useState('{}')
  const [noteText, setNoteText] = useState('')
  const [newTag, setNewTag] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const selectedIdRef = useRef('')

  const queryKey = `${search}:${offset}:${refreshVersion}:${platformFilter}:${statusFilter}`
  const loading = loadedQuery !== queryKey
  useEffect(() => {
    let active = true
    const key = `${search}:${offset}:${refreshVersion}:${platformFilter}:${statusFilter}`
    Promise.all([
      listContacts({
        q: search || undefined,
        platform: platformFilter ? platformFilter as Platform : undefined,
        lead_status: statusFilter ? statusFilter as LeadStatus : undefined,
        offset,
        limit: pageSize,
      }),
      listTags(),
    ]).then(([result, tagList]) => {
      if (!active) return
      if (offset > 0 && offset >= result.total) {
        setOffset(0)
        return
      }
      setContacts(result.items)
      setTotal(result.total)
      setTags(tagList)
      if (selectedIdRef.current && !result.items.some((contact) => contact.id === selectedIdRef.current)) {
        selectedIdRef.current = ''
        setSelected(null)
        setNotes([])
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Contacts could not be loaded.')
    }).finally(() => {
      if (active) setLoadedQuery(key)
    })
    return () => { active = false }
  }, [search, offset, refreshVersion, platformFilter, statusFilter])

  const chooseContact = async (contact: Contact) => {
    selectedIdRef.current = contact.id
    setSelected(contact)
    setEditName(contact.display_name)
    setEditCustomFieldsText(JSON.stringify(contact.custom_fields, null, 2))
    setSelectedTagIds(tags.filter((tag) => contact.tags.includes(tag.name)).map((tag) => tag.id))
    try {
      setNotes(await listContactNotes(contact.id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Contact notes could not be loaded.')
    }
  }

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setNotice('')
    try {
      const customFields = JSON.parse(customFieldsText) as unknown
      if (!customFields || Array.isArray(customFields) || typeof customFields !== 'object') {
        throw new Error('Custom fields must be a JSON object.')
      }
      const created = await createContact({
        social_account_id: accountId,
        platform_customer_id: customerId,
        display_name: name,
        custom_fields: customFields as Record<string, unknown>,
      })
      setNotice('Contact created.')
      setShowCreate(false)
      setCustomerId('')
      setName('')
      setCustomFieldsText('{}')
      setOffset(0)
      setRefreshVersion((value) => value + 1)
      setSelected(created)
      selectedIdRef.current = created.id
      setEditName(created.display_name)
      setEditCustomFieldsText(JSON.stringify(created.custom_fields, null, 2))
      setNotes([])
      setSelectedTagIds([])
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Contact could not be created.')
    }
  }

  const saveContact = async () => {
    if (!selected) return
    try {
      const customFields = JSON.parse(editCustomFieldsText) as unknown
      if (!customFields || Array.isArray(customFields) || typeof customFields !== 'object') {
        throw new Error('Custom fields must be a JSON object.')
      }
      const updated = await updateContact(selected.id, {
        display_name: editName,
        custom_fields: customFields as Record<string, unknown>,
      })
      setSelected(updated)
      setContacts((items) => items.map((item) => item.id === updated.id ? { ...item, display_name: updated.display_name } : item))
      setNotice('Contact updated.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Contact could not be updated.')
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
      setError(reason instanceof Error ? reason.message : 'The note could not be saved.')
    }
  }

  const submitTag = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!newTag.trim()) return
    try {
      const tag = await createTag(newTag)
      setTags((items) => [...items, tag].sort((a, b) => a.name.localeCompare(b.name)))
      setSelectedTagIds((items) => [...items, tag.id])
      setNewTag('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Tag could not be created.')
    }
  }

  const saveTags = async () => {
    if (!selected) return
    try {
      const updated = await replaceContactTags(selected.id, selectedTagIds)
      setSelected(updated)
      setContacts((items) => items.map((item) => item.id === updated.id ? updated : item))
      setNotice('Tags updated.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Tags could not be updated.')
    }
  }

  return <div className="dashboard-page-content crm-page">
    <div className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">WORKSPACE · CRM</span><h1>Contacts</h1><p>Customer records from supported interactions and records added by your team.</p></div>
      {canWrite && <button className="btn btn-primary" type="button" onClick={() => setShowCreate((value) => !value)}><Plus size={15} /> Add contact</button>}
    </div>
    <div className="automation-demo-notice"><span><strong>Customer details are only shown when available from your records and connected account.</strong><small>Platform IDs are displayed when a permitted name or profile detail is unavailable.</small></span></div>
    {notice && <p className="crm-feedback success" role="status">{notice}</p>}
    {error && <p className="crm-feedback error" role="alert">{error}</p>}
    <div className="crm-toolbar">
      <label>Platform<select value={platformFilter} onChange={(event) => { setOffset(0); setPlatformFilter(event.target.value) }}><option value="">All platforms</option><option value="instagram">Instagram</option><option value="facebook">Facebook</option></select></label>
      <label>Lead status<select value={statusFilter} onChange={(event) => { setOffset(0); setStatusFilter(event.target.value) }}><option value="">All statuses</option><option value="new">New</option><option value="interested">Interested</option><option value="qualified">Qualified</option><option value="converted">Converted</option><option value="lost">Lost</option></select></label>
    </div>
    {showCreate && canWrite && <section className="crm-card">
      <div className="crm-card-head"><div><h2>Create a contact</h2><p>Enter platform information you are authorized to manage.</p></div></div>
      <form className="crm-form" onSubmit={(event) => void submitCreate(event)}>
        <label>Connected account<select required value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="">Select an account</option>{availableAccounts.map((account) => <option key={account.id} value={account.id}>{account.platform} · {account.account_name}</option>)}</select></label>
        <label>Platform customer ID<input required value={customerId} onChange={(event) => setCustomerId(event.target.value)} maxLength={255} /></label>
        <label>Customer name (optional)<input value={name} onChange={(event) => setName(event.target.value)} maxLength={200} /></label>
        <label>Custom fields (JSON)<input value={customFieldsText} onChange={(event) => setCustomFieldsText(event.target.value)} /></label>
        <div className="full"><button type="submit" className="crm-button" disabled={!accountId || !customerId.trim()}>Create contact</button></div>
      </form>
    </section>}
    <div className="crm-inbox-grid">
      <section className="crm-card" style={{ gridColumn: selected ? '1 / 3' : '1 / -1' }}>
        <div className="crm-card-head"><div><h2>Contact records</h2><p>{total} contacts</p></div></div>
        <div className="crm-table-wrap">
          <table className="crm-table"><thead><tr><th>Customer</th><th>Platform</th><th>Lead status</th><th>Last interaction</th></tr></thead>
            <tbody>{loading ? <tr><td colSpan={4}>Loading contacts…</td></tr> : contacts.length === 0 ? <tr><td colSpan={4}>No contact records match this search.</td></tr> : contacts.map((contact) => <tr key={contact.id} aria-selected={selected?.id === contact.id} onClick={() => void chooseContact(contact)}>
              <td><span className="crm-name">{contact.display_name || contact.platform_customer_id}</span><br /><span className="crm-muted">{contact.platform_customer_id}</span></td>
              <td><span className="crm-platform">{contact.platform}</span></td>
              <td><span className="crm-status">{contact.lead_status}</span></td>
              <td>{contact.last_interaction_at ? new Date(contact.last_interaction_at).toLocaleDateString() : '—'}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <div className="crm-pagination"><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} of ${total}` : '0 contacts'}</span><span><button className="crm-button ghost" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button> <button className="crm-button ghost" type="button" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next</button></span></div>
      </section>
      {selected && <aside className="crm-card crm-profile">
        <div className="crm-card-head"><div><h2>Contact details</h2><p>{selected.platform} · {selected.platform_customer_id}</p></div><button className="crm-button ghost" type="button" onClick={() => { selectedIdRef.current = ''; setSelected(null) }}>Close</button></div>
        <div className="crm-profile-body">
          <label className="crm-profile-field">Name<input value={editName} disabled={!canWrite} onChange={(event) => setEditName(event.target.value)} /></label>
          <div className="crm-profile-field">First contact<strong>{selected.first_contact_at ? new Date(selected.first_contact_at).toLocaleString() : 'Not available'}</strong></div>
          <label className="crm-profile-field">Custom fields (JSON)<textarea value={editCustomFieldsText} disabled={!canWrite} onChange={(event) => setEditCustomFieldsText(event.target.value)} /></label>
          {canWrite && <button className="crm-button secondary" type="button" onClick={() => void saveContact()}><Save size={13} /> Save contact</button>}
          <div><h3>Tags</h3><div className="crm-tags">{tags.map((tag) => <label className="crm-tag-check" key={tag.id}><input type="checkbox" checked={selectedTagIds.includes(tag.id)} disabled={!canWrite} onChange={(event) => setSelectedTagIds((ids) => event.target.checked ? [...ids, tag.id] : ids.filter((id) => id !== tag.id))} />{tag.name}</label>)}</div>
            {canWrite && <><form className="crm-note-form" onSubmit={(event) => void submitTag(event)}><input aria-label="New tag name" value={newTag} onChange={(event) => setNewTag(event.target.value)} maxLength={60} placeholder="New tag" /><button className="crm-button secondary" type="submit" disabled={!newTag.trim()}>Create tag</button></form><button className="crm-button secondary" type="button" onClick={() => void saveTags()}>Save tags</button></>}
          </div>
          <div><h3>Private notes</h3><div className="crm-note-list">{notes.map((note) => <article className="crm-note" key={note.id}>{note.content}<small className="crm-muted"> · {new Date(note.created_at).toLocaleString()}</small></article>)}</div></div>
          <form className="crm-note-form" onSubmit={(event) => void submitNote(event)}><label htmlFor="contact-note">Add a private note</label><textarea id="contact-note" value={noteText} onChange={(event) => setNoteText(event.target.value)} maxLength={5000} /><button className="crm-button secondary" type="submit" disabled={!noteText.trim()}>Save note</button></form>
        </div>
      </aside>}
    </div>
  </div>
}
