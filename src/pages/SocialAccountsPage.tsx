import { useEffect, useMemo, useState } from 'react'
import { ArrowDownToLine, RefreshCw, ShieldCheck } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { ConnectionStatusBadge } from '../components/dashboard/ConnectionStatusBadge'
import { SocialAccountCard } from '../components/dashboard/SocialAccountCard'
import { useSocialAccounts } from '../hooks/useSocialAccounts'
import {
  disconnectMetaAccount,
  listPendingFacebookPages,
  selectFacebookPage,
  type FacebookPageOption,
  type MetaSocialAccount,
} from '../services/metaApi'
import type { ConnectionStatus, SocialAccount, SocialPlatform } from '../types'

const platforms: SocialPlatform[] = ['instagram', 'facebook']

function displayAccount(account: MetaSocialAccount): SocialAccount {
  const statuses: Record<MetaSocialAccount['connection_status'], ConnectionStatus> = {
    connected: 'Connected',
    expired: 'Authorization Expired',
    disconnected: 'Disconnected',
  }
  return {
    id: account.id,
    platform: account.platform,
    accountName: account.account_name,
    accountType: account.platform === 'instagram' ? 'Instagram Professional' : 'Facebook Page',
    profileImage: null,
    connectionStatus: statuses[account.connection_status],
    connectedAt: account.created_at,
  }
}

export function SocialAccountsPage() {
  const { accounts, loading, error, reload } = useSocialAccounts()
  const [searchParams, setSearchParams] = useSearchParams()
  const [message, setMessage] = useState('')
  const [messageError, setMessageError] = useState(false)
  const [busyAccountId, setBusyAccountId] = useState('')
  const [pages, setPages] = useState<FacebookPageOption[]>([])
  const [selectedPageId, setSelectedPageId] = useState('')
  const [savingPage, setSavingPage] = useState(false)
  const [pagesLoading, setPagesLoading] = useState(true)

  const flowId = searchParams.get('flow_id') || ''
  const pageFlowId = flowId
  const callbackStatus = searchParams.get('oauth_status')
  const callbackError = searchParams.get('oauth_error')

  useEffect(() => {
    if (callbackStatus === 'connected') {
      queueMicrotask(() => {
        setMessage('Meta confirmed the account connection.')
        setMessageError(false)
      })
      setSearchParams({}, { replace: true })
    } else if (callbackError) {
      const errors: Record<string, string> = {
        authorization_denied: 'Meta authorization was cancelled or denied.',
        provider_not_configured: 'Meta connections are not configured for this application.',
        provider_error: 'Meta could not complete the connection. Please try again.',
        invalid_state: 'This authorization request expired or was already used. Start again.',
      }
      queueMicrotask(() => {
        setMessage(errors[callbackError] || 'Meta authorization could not be completed.')
        setMessageError(true)
      })
      setSearchParams({}, { replace: true })
    }
  }, [callbackError, callbackStatus, setSearchParams])

  useEffect(() => {
    if (!flowId) return
    let active = true
    listPendingFacebookPages(flowId)
      .then((result) => {
        if (active) {
          setPages(result)
          setSelectedPageId(result[0]?.platform_account_id || '')
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setMessage(reason instanceof Error ? reason.message : 'Authorized Pages could not be loaded.')
          setMessageError(true)
        }
      })
      .finally(() => { if (active) setPagesLoading(false) })
    return () => { active = false }
  }, [flowId])

  const accountsForDisplay = useMemo(() => accounts.map(displayAccount), [accounts])
  const accountFor = (platform: SocialPlatform) =>
    accountsForDisplay.find((account) => account.platform === platform && account.connectionStatus === 'Connected')
    ?? accountsForDisplay.find((account) => account.platform === platform)
    ?? null

  const handleDisconnect = async (account: SocialAccount) => {
    if (!window.confirm(`Disconnect ${account.accountName}? Existing automations will no longer be able to use this account.`)) return
    setBusyAccountId(account.id)
    setMessage('')
    try {
      await disconnectMetaAccount(account.id)
      setMessage(`${account.accountName} was disconnected.`)
      setMessageError(false)
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'The account could not be disconnected.')
      setMessageError(true)
    } finally {
      setBusyAccountId('')
    }
  }

  const handleRefresh = async () => {
    setMessage('')
    if (await reload()) {
      setMessage('Connection status refreshed from DM Karo.')
      setMessageError(false)
    } else {
      setMessageError(true)
    }
  }

  const handleSelectPage = async () => {
    if (!pageFlowId || !selectedPageId) return
    setSavingPage(true)
    setMessage('')
    try {
      await selectFacebookPage(pageFlowId, selectedPageId)
      setPages([])
      setMessage('Meta confirmed the Facebook Page connection.')
      setMessageError(false)
      setSearchParams({}, { replace: true })
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'The Facebook Page could not be connected.')
      setMessageError(true)
    } finally {
      setSavingPage(false)
    }
  }

  return <div className="dashboard-page-content social-accounts-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">CHANNELS · OFFICIAL META</span><h1>Connect Your Social Accounts</h1><p>Authorize Instagram Professional accounts and Facebook Pages for your organization.</p></div><span className="dashboard-date-chip"><i /> META OAUTH</span></div>
    <div className="social-compliance-banner"><ShieldCheck size={18} /><span><strong>Accounts connect through official Meta authorization.</strong><small>DM Karo never asks for social passwords. Access depends on the permissions granted, Meta app mode, and any required review.</small></span><span>SECURE OAUTH</span></div>
    {(message || error) && <div className={`social-feedback${messageError || error ? ' error' : ''}`} role={messageError || error ? 'alert' : 'status'}>{message || error}</div>}
    {loading && <div className="automation-feedback" role="status">Loading organization accounts…</div>}
    <section className="social-integration-grid" aria-label="Social platform connections">{platforms.map((platform) => <SocialAccountCard key={platform} platform={platform} account={accountFor(platform)} onDisconnect={handleDisconnect} />)}</section>
    {pageFlowId && <section className="dashboard-panel facebook-page-select-panel">
      <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">FACEBOOK LOGIN FOR BUSINESS</span><h2>Select a Facebook Page</h2><p>Choose only from Pages Meta authorized for this connection.</p></div></div>
      {pagesLoading ? <p role="status">Loading authorized Pages…</p> : pages.length > 0 ? <>
        <label className="automation-form-field"><span>Authorized Pages</span><select value={selectedPageId} onChange={(event) => setSelectedPageId(event.target.value)}>{pages.map((page) => <option key={page.platform_account_id} value={page.platform_account_id}>{page.account_name}</option>)}</select></label>
        <button className="btn btn-primary" type="button" onClick={handleSelectPage} disabled={savingPage || !selectedPageId}>{savingPage ? 'Connecting…' : 'Connect selected Page'}</button>
      </> : <p>No Pages were returned for this authorization. Confirm the Page access and permissions in Meta, then try again.</p>}
    </section>}
    <section className="dashboard-panel social-management-panel">
      <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">ORGANIZATION ACCOUNTS</span><h2>Account management</h2><p>Connected account details are retrieved from the backend for your organization.</p></div><button className="social-refresh-button" type="button" onClick={handleRefresh} disabled={loading}><RefreshCw size={14} /> Refresh status</button></div>
      <div className="dashboard-table-scroll"><table className="dashboard-table social-account-table"><thead><tr><th>Platform</th><th>Account name</th><th>Account type</th><th>Status</th><th>Date connected</th><th>Actions</th></tr></thead><tbody>
        {accountsForDisplay.map((account) => <tr key={account.id}>
          <td><span className={`platform-label ${account.platform}`}><i />{account.platform === 'instagram' ? 'Instagram' : 'Facebook'}</span></td>
          <td>{account.accountName}</td>
          <td>{account.accountType}</td>
          <td><ConnectionStatusBadge status={account.connectionStatus} /></td>
          <td>{account.connectedAt ? new Date(account.connectedAt).toLocaleDateString() : '—'}</td>
          <td><div className="social-table-actions">{account.connectionStatus === 'Connected' ? <button type="button" onClick={() => void handleDisconnect(account)} disabled={busyAccountId === account.id}>{busyAccountId === account.id ? 'Disconnecting…' : 'Disconnect'}</button> : <Link to={`/dashboard/accounts/${account.platform}`}>Reconnect <ArrowDownToLine size={12} /></Link>}</div></td>
        </tr>)}
        {!accountsForDisplay.length && !loading && <tr><td colSpan={6}>No accounts are connected to this organization.</td></tr>}
      </tbody></table></div>
      <p className="social-table-note">Only Meta-authorized accounts are listed. Tokens are never returned to the browser.</p>
    </section>
    <p className="social-privacy-note">Instagram connection supports eligible Business and Creator professional accounts. Facebook connection lists Pages granted through Facebook Login for Business. Permissions and production availability depend on Meta review and app configuration.</p>
  </div>
}
