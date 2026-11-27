import { useCallback, useEffect, useState } from 'react'
import { listMetaAccounts, type MetaSocialAccount } from '../services/metaApi'
import { META_ACCOUNTS_CHANGED_EVENT } from '../services/metaEvents'

export function useSocialAccounts() {
  const [accounts, setAccounts] = useState<MetaSocialAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const reload = useCallback(async (): Promise<boolean> => {
    setLoading(true)
    setError('')
    try {
      setAccounts(await listMetaAccounts())
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Social accounts could not be loaded.')
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void reload() }, 0)
    const onChanged = () => { void reload() }
    window.addEventListener(META_ACCOUNTS_CHANGED_EVENT, onChanged)
    return () => {
      window.clearTimeout(initialLoad)
      window.removeEventListener(META_ACCOUNTS_CHANGED_EVENT, onChanged)
    }
  }, [reload])

  return { accounts, loading, error, reload }
}
