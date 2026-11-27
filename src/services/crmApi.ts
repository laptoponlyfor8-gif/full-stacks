import { authenticatedFetch } from './authApi'

export type Platform = 'instagram' | 'facebook'
export type LeadStatus = 'new' | 'interested' | 'qualified' | 'converted' | 'lost'

export type Contact = {
  id: string
  social_account_id: string
  platform: Platform
  platform_customer_id: string
  display_name: string
  lead_status: LeadStatus
  custom_fields: Record<string, unknown>
  first_contact_at: string | null
  last_interaction_at: string | null
  created_at: string
  updated_at: string
  tags: string[]
}

export type Page<T> = { items: T[]; total: number; offset: number; limit: number }
export type Conversation = {
  contact_id: string
  display_name: string
  platform: Platform
  platform_customer_id: string
  latest_message_preview: string
  latest_message_at: string | null
  unread_count: number
  lead_status: LeadStatus
}
export type Message = {
  id: string
  message_type: string
  message_content: string
  delivery_status: string
  external_message_id: string | null
  created_at: string
  platform_created_at: string | null
  is_read: boolean
}
export type ContactNote = { id: string; author_user_id: string; content: string; created_at: string }
export type ConversationDetail = { contact: Contact; messages: Message[]; total: number; offset: number; limit: number }
export type AnalyticsMetric = { value: number; available: boolean }
export type Analytics = {
  date_from: string
  date_to: string
  coverage_start: string | null
  connected_accounts: AnalyticsMetric
  active_automations: AnalyticsMetric
  automation_executions: AnalyticsMetric
  successful_executions: AnalyticsMetric
  failed_executions: AnalyticsMetric
  messages_sent: AnalyticsMetric
  messages_received: AnalyticsMetric
  total_contacts: AnalyticsMetric
  new_leads: AnalyticsMetric
  converted_leads: AnalyticsMetric
  daily_messages: Array<{ date: string; sent: number; received: number }>
  weekly_messages: Array<{ week_start: string; sent: number; received: number }>
  platform_breakdown: Array<{ platform: Platform; sent: number; received: number }>
  automation_performance: Array<{ automation_id: string; name: string; executions: number; successful: number; failed: number }>
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: new Headers({
      'Content-Type': 'application/json',
      ...Object.fromEntries(new Headers(init?.headers).entries()),
    }),
  })
  const data = response.status === 204 ? undefined : await response.json().catch(() => undefined)
  if (!response.ok) {
    const body = data as { detail?: string; error?: { message?: string } } | undefined
    throw new Error(body?.error?.message || body?.detail || 'The request could not be completed.')
  }
  return data as T
}

function queryString(values: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  const encoded = query.toString()
  return encoded ? `?${encoded}` : ''
}

export function listConversations(params: { q?: string; platform?: Platform; lead_status?: LeadStatus; offset?: number; limit?: number } = {}) {
  return request<Page<Conversation>>(`/conversations${queryString(params)}`)
}

export function getConversation(id: string, offset = 0, limit = 100) {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}${queryString({ offset, limit })}`)
}

export function markConversationRead(id: string) {
  return request<void>(`/conversations/${encodeURIComponent(id)}/read`, { method: 'PATCH' })
}

export function sendMessage(id: string, text: string, idempotencyKey: string) {
  return request<Message>(`/conversations/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    body: JSON.stringify({ text, idempotency_key: idempotencyKey }),
  })
}

export function listContacts(params: { q?: string; lead_status?: LeadStatus; platform?: Platform; offset?: number; limit?: number } = {}) {
  return request<Page<Contact>>(`/contacts${queryString(params)}`)
}

export function createContact(input: {
  social_account_id: string
  platform_customer_id: string
  display_name: string
  custom_fields: Record<string, unknown>
}) {
  return request<Contact>('/contacts', { method: 'POST', body: JSON.stringify(input) })
}

export function updateContact(id: string, updates: { display_name?: string; custom_fields?: Record<string, unknown> }) {
  return request<Contact>(`/contacts/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
}

export function listContactNotes(id: string) {
  return request<ContactNote[]>(`/contacts/${encodeURIComponent(id)}/notes`)
}

export function addContactNote(id: string, content: string) {
  return request<ContactNote>(`/contacts/${encodeURIComponent(id)}/notes`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export function listTags() {
  return request<Array<{ id: string; name: string; created_at: string }>>('/tags')
}

export function createTag(name: string) {
  return request<{ id: string; name: string; created_at: string }>('/tags', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export function replaceContactTags(id: string, tagIds: string[]) {
  return request<Contact>(`/contacts/${encodeURIComponent(id)}/tags`, {
    method: 'PUT',
    body: JSON.stringify({ tag_ids: tagIds }),
  })
}

export function updateLeadStatus(id: string, lead_status: LeadStatus) {
  return request<Contact>(`/leads/${encodeURIComponent(id)}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status: lead_status }),
  })
}

export function listLeads(params: { q?: string; lead_status?: LeadStatus; offset?: number; limit?: number } = {}) {
  return request<Page<Contact>>(`/leads${queryString(params)}`)
}

export function listLeadActivities(id: string) {
  return request<Array<{ id: string; activity_type: string; detail: string; created_at: string }>>(
    `/leads/${encodeURIComponent(id)}/activities`,
  )
}

export function getAnalytics(params: { date_from?: string; date_to?: string } = {}) {
  return request<Analytics>(`/analytics${queryString(params)}`)
}
