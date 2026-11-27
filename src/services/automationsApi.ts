import { authenticatedFetch } from './authApi'
import type { Automation, AutomationDraftInput, AutomationStatus, KeywordMatchMethod } from '../types'

type ApiKeyword = { keyword: string; match_type: 'exact' | 'contains' | 'phrase' }
type ApiAutomation = {
  id: string
  social_account_id: string
  platform: 'instagram' | 'facebook'
  account_name: string
  name: string
  trigger_type: 'comment' | 'direct_message'
  content_type: string
  content_url: string
  status: 'draft' | 'active' | 'paused' | 'archived'
  keywords: ApiKeyword[]
  private_reply_text: string | null
  public_reply_enabled: boolean
  public_reply_text: string | null
  created_at: string
  updated_at: string
  executions: number
  sent_messages: number
  failed_messages: number
}

export type AutomationInput = {
  name: string
  social_account_id: string
  platform: 'instagram' | 'facebook'
  content_type: string
  content_url: string
  trigger_type?: 'comment' | 'direct_message'
}

export type AutomationConfiguration = {
  keywords: Array<{ keyword: string; match_type: ApiKeyword['match_type'] }>
  private_reply_text: string | null
  public_reply_enabled: boolean
  public_reply_text: string | null
}
type AutomationPatch = Partial<AutomationInput> & Partial<AutomationConfiguration> & {
  status?: ApiAutomation['status']
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
    throw new Error(body?.error?.message || body?.detail || 'The automation request could not be completed.')
  }
  return data as T
}

export async function listAutomations(): Promise<Automation[]> {
  return (await request<ApiAutomation[]>('/automations')).map(fromApi)
}

export async function getAutomation(id: string): Promise<Automation> {
  return fromApi(await request<ApiAutomation>(`/automations/${encodeURIComponent(id)}`))
}

export async function createAutomation(input: AutomationInput): Promise<Automation> {
  return fromApi(await request<ApiAutomation>('/automations', {
    method: 'POST',
    body: JSON.stringify({
      ...input,
      keywords: [],
      private_reply_text: null,
      public_reply_enabled: false,
      public_reply_text: null,
    }),
  }))
}

export async function updateAutomation(
  id: string,
  updates: AutomationPatch,
): Promise<Automation> {
  return fromApi(await request<ApiAutomation>(`/automations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  }))
}

export async function changeAutomationStatus(id: string, status: AutomationStatus): Promise<Automation> {
  return updateAutomation(id, { status: status.toLowerCase() as ApiAutomation['status'] })
}

export async function removeAutomation(id: string): Promise<void> {
  await request<void>(`/automations/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

function fromApi(value: ApiAutomation): Automation {
  const matchingMethod = toMatchMethod(value.keywords[0]?.match_type)
  const publicReply = value.public_reply_text || ''
  return {
    id: value.id,
    name: value.name,
    platform: value.platform === 'instagram' ? 'Instagram' : 'Facebook',
    accountId: value.social_account_id,
    accountName: value.account_name,
    contentType: value.content_type as Automation['contentType'],
    postUrl: value.content_url,
    triggerType: value.trigger_type,
    status: titleStatus(value.status),
    createdAt: value.created_at,
    updatedAt: value.updated_at,
    privateReplyText: value.private_reply_text || '',
    executions: value.executions,
    sentMessages: value.sent_messages,
    failedMessages: value.failed_messages,
    commentTrigger: {
      keywords: value.keywords.map((item) => item.keyword),
      matchingMethod,
      keywordRulesEnabled: value.keywords.length > 0,
      ignoreAccountOwner: true,
      ignoreDuplicateEvents: true,
      ignoreCommentsWithoutKeywords: true,
      preventRepeatedCommentAutomation: true,
      publicReplyEnabled: value.public_reply_enabled,
      publicReplyVariations: publicReply ? [publicReply] : [],
      customPublicReply: publicReply,
      updatedAt: value.updated_at,
    },
  }
}

function toMatchMethod(value: ApiKeyword['match_type'] | undefined): KeywordMatchMethod {
  if (value === 'exact') return 'exact'
  if (value === 'phrase') return 'any-phrase'
  return 'contains'
}

function titleStatus(value: ApiAutomation['status']): AutomationStatus {
  return value === 'active' ? 'Active' : value === 'paused' ? 'Paused' : value === 'archived' ? 'Needs setup' : 'Draft'
}

export function automationConfiguration(
  keywords: string[],
  method: KeywordMatchMethod,
  privateReplyText: string,
  publicReplyEnabled: boolean,
  publicReplyText: string,
): AutomationConfiguration {
  const matchType = method === 'any-phrase' ? 'phrase' : method
  return {
    keywords: keywords.map((keyword) => ({ keyword, match_type: matchType })),
    private_reply_text: privateReplyText.trim() || null,
    public_reply_enabled: publicReplyEnabled,
    public_reply_text: publicReplyEnabled ? publicReplyText.trim() || null : null,
  }
}

export function automationInput(draft: AutomationDraftInput, accountId: string): AutomationInput {
  return {
    name: draft.name,
    social_account_id: accountId,
    platform: draft.platform.toLowerCase() as AutomationInput['platform'],
    content_type: draft.contentType,
    content_url: draft.postUrl,
    trigger_type: draft.triggerType ?? 'comment',
  }
}
