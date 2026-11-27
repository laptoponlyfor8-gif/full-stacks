import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { AuthContext } from './AuthContextValue'
import {
  login as apiLogin,
  logout as apiLogout,
  refreshSession,
  register as apiRegister,
  type AuthUser,
} from '../services/authApi'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    refreshSession()
      .then((response) => { if (active) setUser(response?.user ?? null) })
      .catch(() => { if (active) setUser(null) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  const login = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    const response = await apiLogin(email, password, rememberMe)
    setUser(response.user)
    return response.user
  }, [])

  const register = useCallback((input: Parameters<typeof apiRegister>[0]) => apiRegister(input), [])

  const logout = useCallback(async () => {
    await apiLogout()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
