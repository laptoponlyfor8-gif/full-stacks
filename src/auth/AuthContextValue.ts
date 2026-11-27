import { createContext } from 'react'
import type { AuthUser, RegistrationResponse } from '../services/authApi'
import type { register as apiRegister } from '../services/authApi'

export type AuthContextValue = {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string, rememberMe: boolean) => Promise<AuthUser>
  register: (input: Parameters<typeof apiRegister>[0]) => Promise<RegistrationResponse>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
