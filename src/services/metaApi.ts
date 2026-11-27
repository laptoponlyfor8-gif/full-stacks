import { authenticatedFetch } from './authApi'
import { notifyMetaAccountsChanged } from './metaEvents'
import type { SocialPlatform } from '../types'

export type MetaSocialAccount = {
  id: string
  platform: SocialPlatform
  platform_account_id: string
  account_name: string
  created_at: string
  token_expires_at: string | null
  is_connected: boolean
  connection_status: 'connected' | 'expired' | 'disconnected'
}

export type FacebookPageOption = {
  platform_account_id: string
  account_name: string
}

type ApiError = {
  error?: { message?: string }
  detail?: string
}

async function readResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => ({})) as ApiError & T
  if (!response.ok) {
    throw new Error(data.error?.message || data.detail || 'The Meta account request could not be completed.')
  }
  return data
}

export async function listMetaAccounts(): Promise<MetaSocialAccount[]> {
  return readResponse(await authenticatedFetch('/meta/accounts'))
}

export async function startMetaConnection(platform: SocialPlatform): Promise<string> {
  const response = await authenticatedFetch(`/meta/connect/${platform}`, { method: 'POST' })
  const result = await readResponse<{ authorization_url: string }>(response)
  return result.authorization_url
}

export async function disconnectMetaAccount(accountId: string): Promise<void> {
  await readResponse(await authenticatedFetch(`/meta/accounts/${encodeURIComponent(accountId)}`, {
    method: 'DELETE',
  }))
  notifyMetaAccountsChanged()
}

export async function refreshMetaAccount(accountId: string): Promise<MetaSocialAccount> {
  const account = await readResponse<MetaSocialAccount>(await authenticatedFetch(`/meta/accounts/${encodeURIComponent(accountId)}/refresh`, {
    method: 'POST',
  }))
  notifyMetaAccountsChanged()
  return account
}

export async function listPendingFacebookPages(flowId: string): Promise<FacebookPageOption[]> {
  return readResponse(await authenticatedFetch(
    `/meta/facebook/pending/${encodeURIComponent(flowId)}/pages`,
  ))
}

export async function selectFacebookPage(
  flowId: string,
  platformAccountId: string,
): Promise<MetaSocialAccount> {
  const account = await readResponse<MetaSocialAccount>(await authenticatedFetch(
    `/meta/facebook/pending/${encodeURIComponent(flowId)}/select`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ platform_account_id: platformAccountId }),
    },
  ))
  notifyMetaAccountsChanged()
  return account
}
