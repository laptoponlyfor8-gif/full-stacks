import { useEffect, useRef, useState } from 'react'
import { MessageSquare, Send } from 'lucide-react'
import { useLocation, useOutletContext } from 'react-router-dom'
import { addContactNote, getConversation, listContactNotes, listConversations, markConversationRead, sendMessage } from '../services/crmApi'
import type { ContactNote, Conversation, ConversationDetail, LeadStatus } from '../services/crmApi'
import type { DashboardContext } from './DashboardOverviewPage'
import '../crm.css'

const leadLabels: Record<LeadStatus, string> = {
  new: 'New', interested: 'Interested', qualified: 'Qualified', converted: 'Converted', lost: 'Lost',
}

function formatTime(value: string | null): string {
  if (!value) return 'Time unavailable'
  return new Date(value).toLocaleString()
}

export function InboxPage() {
  const { search } = useOutletContext<DashboardContext>()
  const location = useLocation()
  const requestedContactId = new URLSearchParams(location.search).get('contact') || ''
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [notes, setNotes] = useState<ContactNote[]>([])
  const [messageText, setMessageText] = useState('')
  const [noteText, setNoteText] = useState('')
  const [sending, setSending] = useState(false)
  const [offset, setOffset] = useState(0)
  const [total, setTotal] = useState(0)
  const [platformFilter, setPlatformFilter] = useState('')
  const [leadFilter, setLeadFilter] = useState('')
  const [error, setError] = useState('')
  const selectedIdRef = useRef('')
  const manualAttemptRef = useRef<{ text: string; key: string } | null>(null)
  const queryKey = `${search}:${offset}:${location.search}:${platformFilter}:${leadFilter}`
  const [loadedQuery, setLoadedQuery] = useState('')
  const loading = loadedQuery !== queryKey

  const loadList = async (keepSelection = true) => {
    setError('')
    try {
      const result = await listConversations({
        q: search || undefined,
        platform: platformFilter ? platformFilter as 'instagram' | 'facebook' : undefined,
        lead_status: leadFilter ? leadFilter as LeadStatus : undefined,
        offset,
        limit: 30,
      })
      setConversations(result.items)
      setTotal(result.total)
      const currentSelection = selectedIdRef.current
      const nextId = keepSelection && result.items.some((item) => item.contact_id === currentSelection)
        ? currentSelection
        : result.items[0]?.contact_id ?? ''
      selectedIdRef.current = nextId
      setSelectedId(nextId)
      if (nextId) await loadConversation(nextId)
      else { setDetail(null); setNotes([]) }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Conversations could not be loaded.')
    } finally {
      setLoadedQuery(queryKey)
    }
  }

  const loadConversation = async (id: string) => {
    try {
      const current = await getConversation(id)
      setDetail(current)
      const fetchedNotes = await listContactNotes(id)
      setNotes(fetchedNotes)
      if (current.messages.some((item) => item.message_type === 'incoming' && !item.is_read)) {
        await markConversationRead(id)
        setConversations((items) => items.map((item) => item.contact_id === id ? { ...item, unread_count: 0 } : item))
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The conversation could not be loaded.')
    }
  }

  useEffect(() => {
    let active = true
    const key = `${search}:${offset}:${location.search}:${platformFilter}:${leadFilter}`
    listConversations({
      q: search || undefined,
      platform: platformFilter ? platformFilter as 'instagram' | 'facebook' : undefined,
      lead_status: leadFilter ? leadFilter as LeadStatus : undefined,
      offset,
      limit: 30,
    })
      .then(async (result) => {
        if (!active) return
        if (offset > 0 && offset >= result.total) {
          setOffset(0)
          return
        }
        setConversations(result.items)
        setTotal(result.total)
        const nextId = result.items.some((item) => item.contact_id === requestedContactId)
          ? requestedContactId
          : result.items.some((item) => item.contact_id === selectedIdRef.current)
          ? selectedIdRef.current
          : result.items[0]?.contact_id ?? ''
        selectedIdRef.current = nextId
        setSelectedId(nextId)
        if (nextId) {
          const current = await getConversation(nextId)
          if (active) {
            setDetail(current)
            setNotes(await listContactNotes(nextId))
            if (current.messages.some((item) => item.message_type === 'incoming' && !item.is_read)) {
              await markConversationRead(nextId)
            }
          }
        } else if (active) {
          setDetail(null)
          setNotes([])
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Conversations could not be loaded.')
      })
      .finally(() => { if (active) setLoadedQuery(key) })
    return () => { active = false }
  }, [search, offset, location.search, requestedContactId, platformFilter, leadFilter])

  const selectConversation = async (id: string) => {
    selectedIdRef.current = id
    setSelectedId(id)
    setError('')
    await loadConversation(id)
  }

  const submitMessage = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!detail || !messageText.trim()) return
    setSending(true)
    setError('')
    try {
      if (!manualAttemptRef.current || manualAttemptRef.current.text !== messageText) {
        manualAttemptRef.current = { text: messageText, key: crypto.randomUUID() }
      }
      await sendMessage(detail.contact.id, messageText, manualAttemptRef.current.key)
      manualAttemptRef.current = null
      setMessageText('')
      await loadConversation(detail.contact.id)
      await loadList()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Meta did not confirm the message.')
      if (detail) await loadConversation(detail.contact.id)
    } finally {
      setSending(false)
    }
  }

  const submitNote = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!detail || !noteText.trim()) return
    setError('')
    try {
      const note = await addContactNote(detail.contact.id, noteText)
      setNotes((items) => [note, ...items])
      setNoteText('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The note could not be saved.')
    }
  }

  return <div className="dashboard-page-content crm-page">
    <div className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">WORKSPACE · MESSAGING</span><h1>Unified Inbox</h1><p>Conversations captured from connected Meta webhook events.</p></div>
      <span className="dashboard-date-chip"><i /> LIVE ACCOUNT DATA</span>
    </div>
    <div className="automation-demo-notice"><span><strong>Conversation history starts when supported webhooks are received.</strong><small>Older conversations are not imported here. Reply availability depends on Meta’s account permissions and messaging window.</small></span></div>
    {error && <p className="crm-feedback error" role="alert">{error}</p>}
    <div className="crm-toolbar">
      <label>Platform<select value={platformFilter} onChange={(event) => { setOffset(0); setPlatformFilter(event.target.value) }}><option value="">All platforms</option><option value="instagram">Instagram</option><option value="facebook">Facebook</option></select></label>
      <label>Lead status<select value={leadFilter} onChange={(event) => { setOffset(0); setLeadFilter(event.target.value) }}><option value="">All statuses</option>{Object.entries(leadLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
    </div>
    <div className="crm-inbox-grid">
      <section className="crm-card">
        <div className="crm-card-head"><div><h2>Conversations</h2><p>{conversations.length} loaded</p></div></div>
        <div className="crm-conversation-list" aria-label="Conversation list">
          {loading ? <p className="crm-empty" role="status">Loading conversations…</p> : conversations.length === 0
            ? <p className="crm-empty">No recorded conversations yet.</p>
            : conversations.map((item) => <button
              type="button"
              className="crm-conversation-row"
              key={item.contact_id}
              aria-current={selectedId === item.contact_id}
              onClick={() => void selectConversation(item.contact_id)}
            >
              <span className="crm-conversation-top"><strong className="crm-name">{item.display_name || item.platform_customer_id}</strong>{item.unread_count > 0 && <span className="crm-unread">{item.unread_count}</span>}</span>
              <span className="crm-conversation-preview">{item.latest_message_preview}</span>
              <span className="crm-conversation-meta"><span className="crm-platform">{item.platform}</span><small className="crm-muted">{formatTime(item.latest_message_at)}</small></span>
            </button>)}
        </div>
        <div className="crm-pagination"><span>{total ? `${offset + 1}–${Math.min(offset + 30, total)} of ${total}` : '0 conversations'}</span><span><button className="crm-button ghost" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 30))}>Prev</button> <button className="crm-button ghost" type="button" disabled={offset + 30 >= total} onClick={() => setOffset(offset + 30)}>Next</button></span></div>
      </section>

      <section className="crm-card crm-chat" aria-label="Selected conversation">
        <div className="crm-card-head">
          <div><h2>{detail?.contact.display_name || detail?.contact.platform_customer_id || 'Select a conversation'}</h2><p>{detail ? `${detail.contact.platform} · ${detail.contact.platform_customer_id}` : 'Messages from connected accounts appear here.'}</p></div>
          {detail && <span className="crm-status">{leadLabels[detail.contact.lead_status]}</span>}
        </div>
        <div className="crm-chat-history" aria-live="polite">
          {detail?.messages.length ? detail.messages.map((message) => {
            const outgoing = message.message_type !== 'incoming'
            return <article className={`crm-message${outgoing ? ' outgoing' : ''}`} key={message.id}>
              {message.message_content}
              <small>{formatTime(message.platform_created_at || message.created_at)} · {outgoing ? message.delivery_status : 'received'}</small>
            </article>
          }) : <p className="crm-empty"><MessageSquare size={22} /><br />No stored messages in this conversation.</p>}
        </div>
        <form className="crm-composer" onSubmit={(event) => void submitMessage(event)}>
          <textarea aria-label="Reply message" value={messageText} onChange={(event) => { const text = event.target.value; setMessageText(text); if (manualAttemptRef.current?.text !== text) manualAttemptRef.current = null }} maxLength={1000} placeholder="Write a reply…" disabled={!detail || sending} />
          <button className="crm-button" type="submit" disabled={!detail || !messageText.trim() || sending} aria-label="Send reply">{sending ? 'Sending…' : <><Send size={14} /> Send</>}</button>
        </form>
      </section>

      <aside className="crm-card crm-profile">
        <div className="crm-card-head"><div><h2>Customer profile</h2><p>Information available to this workspace</p></div></div>
        {detail ? <div className="crm-profile-body">
          <div className="crm-profile-field">Name<strong>{detail.contact.display_name || 'Not provided by Meta'}</strong></div>
          <div className="crm-profile-field">Platform ID<strong>{detail.contact.platform_customer_id}</strong></div>
          <div className="crm-profile-field">First contact<strong>{formatTime(detail.contact.first_contact_at)}</strong></div>
          <div className="crm-profile-field">Last interaction<strong>{formatTime(detail.contact.last_interaction_at)}</strong></div>
          {detail.contact.tags.length > 0 && <div><h3>Tags</h3><div className="crm-tags">{detail.contact.tags.map((tag) => <span className="crm-status" key={tag}>{tag}</span>)}</div></div>}
          <div><h3>Notes</h3><div className="crm-note-list">{notes.map((note) => <div className="crm-note" key={note.id}>{note.content}<small className="crm-muted"> · {formatTime(note.created_at)}</small></div>)}</div></div>
          <form className="crm-note-form" onSubmit={(event) => void submitNote(event)}>
            <label htmlFor="inbox-note">Add a private note</label>
            <textarea id="inbox-note" value={noteText} onChange={(event) => setNoteText(event.target.value)} maxLength={5000} />
            <button type="submit" className="crm-button secondary" disabled={!noteText.trim()}>Save note</button>
          </form>
        </div> : <p className="crm-empty">Select a conversation to view permitted profile details.</p>}
      </aside>
    </div>
  </div>
}
