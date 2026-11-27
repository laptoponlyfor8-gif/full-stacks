import { Camera, ChevronDown, MessageCircle } from 'lucide-react'
import { useMemo } from 'react'
import { useSocialAccounts } from '../../hooks/useSocialAccounts'
import type { SocialPlatform } from '../../types'

export function SocialAccountSelector({ value, onChange, label = 'Social account', platform }: { value: string; onChange: (accountId: string) => void; label?: string; platform?: SocialPlatform }) {
  const { accounts, loading, error } = useSocialAccounts()
  const selectable = useMemo(
    () => accounts.filter((account) => account.is_connected && account.connection_status === 'connected' && (!platform || account.platform === platform)),
    [accounts, platform],
  )

  return <label className="social-account-selector">
    <span>{label} <i>META ACCOUNTS</i></span>
    <span className="social-selector-control">
      {value && (selectable.find((account) => account.id === value)?.platform === 'instagram' ? <Camera size={16} /> : <MessageCircle size={16} />)}
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        <option value="">{loading ? 'Loading accounts…' : 'Select a connected account'}</option>
        {selectable.map((account) => <option value={account.id} key={account.id}>{account.platform === 'instagram' ? 'Instagram' : 'Facebook'} · {account.account_name}</option>)}
      </select>
      <ChevronDown size={15} />
    </span>
    {error && <small role="alert">{error}</small>}
    {!selectable.length && !loading && !error && <small>No Meta accounts are connected yet. Connect one from Social Accounts.</small>}
    {selectable.length > 0 && <small>Only active Meta connections for this organization are available.</small>}
  </label>
}
