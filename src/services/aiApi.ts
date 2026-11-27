import { authenticatedFetch } from './authApi'

export type AIProvider = 'openai' | 'gemini'
export type AIAction = 'draft_message' | 'suggest_keywords' | 'public_reply' | 'improve_message' | 'translate' | 'summarize' | 'suggested_reply' | 'classify'
export type AIMessage = { id: string; role: 'user' | 'assistant'; content: string; provider: string | null; model: string | null; created_at: string }
export type AIConversation = { id: string; title: string; updated_at: string; messages: AIMessage[] }
export type AIProviderStatus = { provider: AIProvider; configured: boolean; model: string }
export type AISettings = { providers: AIProviderStatus[]; selected_provider: AIProvider | null; selected_model: string | null }
export type AIUsage = {
  since: string
  until: string
  request_count: number
  successful_count: number
  failed_count: number
  input_tokens: number
  output_tokens: number
  estimated_cost_usd: number | null
  daily_request_limit: number
}
export type AIKnowledge = {
  business_name: string
  description: string
  products_services: string
  faqs: string
  website_information: string
  custom_instructions: string
  updated_at: string | null
}
export type AIResult = { result: string; provider: AIProvider; model: string; input_tokens: number | null; output_tokens: number | null; estimated_cost_usd: number | null }

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
    throw new Error(body?.error?.message || body?.detail || 'The AI request could not be completed.')
  }
  return data as T
}

export const getAISettings = () => request<AISettings>('/ai/providers')

export const updateAISettings = (provider: AIProvider, model: string) => request<AISettings>('/ai/providers', {
  method: 'PUT',
  body: JSON.stringify({ provider, model }),
})

export const listAIConversations = () => request<AIConversation[]>('/ai/conversations')

export const getAIConversation = (id: string) => request<AIConversation>(`/ai/conversations/${encodeURIComponent(id)}`)

export const clearAIConversation = (id: string) => request<void>(`/ai/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const sendAIMessage = (message: string, conversationId?: string) => request<{
  conversation_id: string
  answer: string
  provider: AIProvider
  model: string
  input_tokens: number | null
  output_tokens: number | null
  estimated_cost_usd: number | null
}>('/ai/chat', {
  method: 'POST',
  body: JSON.stringify({ message, conversation_id: conversationId }),
})

export const askAIAssist = (action: AIAction, inputText: string, context = '', language = '') => request<AIResult>('/ai/assist', {
  method: 'POST',
  body: JSON.stringify({ action, input_text: inputText, context, language }),
})

export const getAIUsage = () => request<AIUsage>('/ai/usage')

export const getAIKnowledge = () => request<AIKnowledge>('/ai/knowledge')

export const saveAIKnowledge = (knowledge: Omit<AIKnowledge, 'updated_at'>) => request<AIKnowledge>('/ai/knowledge', {
  method: 'PUT',
  body: JSON.stringify(knowledge),
})
