import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <main className="auth-page" aria-live="polite"><p className="auth-loading">Checking your session…</p></main>
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  return children
}

export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <main className="auth-page" aria-live="polite"><p className="auth-loading">Checking your session…</p></main>
  if (user) return <Navigate to="/dashboard" replace />
  return children
}
