import { Navigate, useSearchParams } from 'react-router-dom'

export function MessageBuilderPage() {
  const [searchParams] = useSearchParams()
  const id = searchParams.get('id')
  return <Navigate
    to={id ? `/dashboard/automations/configure?id=${encodeURIComponent(id)}` : '/dashboard/automations'}
    replace
  />
}
