import type { Automation, AutomationDraftInput, AutomationStatus, CommentTriggerConfiguration, KeywordMatchMethod } from '../types'

const storageKey = 'dm-karo-demo-automations'
const automationChangedEvent = 'dm-karo-demo-automations-changed'
const statuses: AutomationStatus[] = ['Draft', 'Active', 'Paused', 'Needs setup']
const matchMethods: KeywordMatchMethod[] = ['exact', 'contains', 'any-phrase']

function isCommentTriggerConfiguration(value: unknown): value is CommentTriggerConfiguration {
  if (typeof value !== 'object' || value === null) return false
  if (!('keywords' in value) || !('matchingMethod' in value) || !('keywordRulesEnabled' in value)
    || !('ignoreAccountOwner' in value) || !('ignoreDuplicateEvents' in value)
    || !('ignoreCommentsWithoutKeywords' in value) || !('preventRepeatedCommentAutomation' in value)
    || !('publicReplyEnabled' in value) || !('publicReplyVariations' in value)
    || !('customPublicReply' in value) || !('updatedAt' in value)) return false
  return Array.isArray(value.keywords) && value.keywords.every((keyword) => typeof keyword === 'string' && Boolean(keyword.trim()))
    && matchMethods.includes(value.matchingMethod as KeywordMatchMethod)
    && typeof value.keywordRulesEnabled === 'boolean'
    && typeof value.ignoreAccountOwner === 'boolean'
    && typeof value.ignoreDuplicateEvents === 'boolean'
    && typeof value.ignoreCommentsWithoutKeywords === 'boolean'
    && typeof value.preventRepeatedCommentAutomation === 'boolean'
    && typeof value.publicReplyEnabled === 'boolean'
    && Array.isArray(value.publicReplyVariations) && value.publicReplyVariations.every((reply) => typeof reply === 'string')
    && typeof value.customPublicReply === 'string'
    && typeof value.updatedAt === 'string'
}

function isAutomation(value: unknown): value is Automation {
  if (typeof value !== 'object' || value === null) return false
  if (!('id' in value) || !('name' in value) || !('platform' in value) || !('accountId' in value)
    || !('accountName' in value) || !('contentType' in value) || !('postUrl' in value)
    || !('status' in value) || !('createdAt' in value) || !('updatedAt' in value)) return false

  return typeof value.id === 'string'
    && typeof value.name === 'string'
    && (value.platform === 'Instagram' || value.platform === 'Facebook')
    && typeof value.accountId === 'string'
    && typeof value.accountName === 'string'
    && (value.contentType === 'Instagram Reel' || value.contentType === 'Instagram Post' || value.contentType === 'Facebook Post')
    && typeof value.postUrl === 'string'
    && statuses.includes(value.status as AutomationStatus)
    && (!('commentTrigger' in value) || value.commentTrigger === undefined || isCommentTriggerConfiguration(value.commentTrigger))
    && typeof value.createdAt === 'string'
    && typeof value.updatedAt === 'string'
}

function emitChange(): void {
  window.dispatchEvent(new Event(automationChangedEvent))
}

export function subscribeToAutomations(onChange: () => void): () => void {
  window.addEventListener(automationChangedEvent, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(automationChangedEvent, onChange)
    window.removeEventListener('storage', onChange)
  }
}

export function getAutomations(): Automation[] {
  const saved = localStorage.getItem(storageKey)
  if (!saved) return []

  let parsed: unknown
  try {
    parsed = JSON.parse(saved)
  } catch {
    throw new Error('Saved demo automation data is invalid. Clear this site’s local storage and try again.')
  }
  if (!Array.isArray(parsed) || !parsed.every(isAutomation)) {
    throw new Error('Saved demo automation data contains an invalid record.')
  }
  return parsed
}

function writeAutomations(automations: Automation[]): void {
  localStorage.setItem(storageKey, JSON.stringify(automations))
  emitChange()
}

function createId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `demo-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function saveAutomationDraft(input: AutomationDraftInput, id?: string): Automation {
  const existing = id ? getAutomations().find((automation) => automation.id === id) : undefined
  const timestamp = new Date().toISOString()
  const automation: Automation = {
    ...input,
    commentTrigger: input.commentTrigger ?? existing?.commentTrigger,
    id: existing?.id ?? createId(),
    status: 'Draft',
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
  }
  const automations = getAutomations()
  writeAutomations([...automations.filter((item) => item.id !== automation.id), automation])
  return automation
}

export function updateAutomation(id: string, input: AutomationDraftInput): Automation {
  return saveAutomationDraft(input, id)
}

export function saveCommentTriggerConfiguration(id: string, configuration: Omit<CommentTriggerConfiguration, 'updatedAt'>): Automation {
  const automations = getAutomations()
  const existing = automations.find((automation) => automation.id === id)
  if (!existing) throw new Error('This demo automation could not be found. Return to My Automations and try again.')
  const updated: Automation = {
    ...existing,
    commentTrigger: { ...configuration, updatedAt: new Date().toISOString() },
    updatedAt: new Date().toISOString(),
  }
  writeAutomations(automations.map((automation) => automation.id === id ? updated : automation))
  return updated
}

export function deleteAutomation(id: string): void {
  writeAutomations(getAutomations().filter((automation) => automation.id !== id))
}

export function getAutomationById(id: string): Automation | null {
  return getAutomations().find((automation) => automation.id === id) ?? null
}

export function getActiveAutomationCount(): number {
  return getAutomations().filter((automation) => automation.status === 'Active').length
}
