export type AuthOrganization = {
  id: string
  name: string
  slug: string
  role: 'owner' | 'admin' | 'member'
}

export type AuthUser = {
  id: string
  name: string
  email: string
  email_verified: boolean
  organization: AuthOrganization
}

export type AuthResponse = {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export type RegistrationResponse = {
  id: string
  email: string
  email_verification_sent: boolean
  message: string
}

type ApiErrorBody = {
  error?: { code?: string; message?: string; fields?: Array<{ field: string; message: string }> }
  detail?: string
}

export class AuthApiError extends Error {
  readonly code: string
  readonly status: number
  readonly fields: Array<{ field: string; message: string }>

  constructor(message: string, status: number, code: string, fields: Array<{ field: string; message: string }> = []) {
    super(message)
    this.name = 'AuthApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
let accessToken: string | null = null
let refreshInFlight: Promise<AuthResponse | null> | null = null

function csrfToken(): string {
  const entry = document.cookie.split('; ').find((cookie) => cookie.startsWith('dm_csrf='))
  return entry ? decodeURIComponent(entry.slice('dm_csrf='.length)) : ''
}

function storeToken(response: AuthResponse): AuthResponse {
  accessToken = response.access_token
  return response
}

function clearToken(): void {
  accessToken = null
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => ({})) as ApiErrorBody & T
  if (!response.ok) {
    const message = data.error?.message || data.detail || 'The request could not be completed.'
    const code = response.headers.get('X-Auth-Error') || data.error?.code || 'request_failed'
    throw new AuthApiError(message, response.status, code, data.error?.fields)
  }
  return data
}

async function post<T>(path: string, payload?: unknown, csrf = false): Promise<T> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (csrf) headers.set('X-CSRF-Token', csrfToken())
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
  return parseResponse<T>(response)
}

export function login(email: string, password: string, rememberMe: boolean): Promise<AuthResponse> {
  return post<AuthResponse>('/auth/login', { email, password, remember_me: rememberMe }).then(storeToken)
}

export function register(input: {
  name: string
  business_name: string
  email: string
  mobile_number: string
  password: string
  confirm_password: string
}): Promise<RegistrationResponse> {
  return post<RegistrationResponse>('/auth/register', input)
}

export function refreshSession(): Promise<AuthResponse | null> {
  if (refreshInFlight) return refreshInFlight
  if (!csrfToken()) return Promise.resolve(null)
  refreshInFlight = post<AuthResponse>('/auth/refresh', {}, true)
    .then(storeToken)
    .catch((error: unknown) => {
      clearToken()
      if (error instanceof AuthApiError && error.status === 401) return null
      throw error
    })
    .finally(() => { refreshInFlight = null })
  return refreshInFlight
}

export async function logout(): Promise<void> {
  try {
    await post<void>('/auth/logout', undefined, true)
  } finally {
    clearToken()
  }
}

export function requestPasswordReset(email: string): Promise<{ message: string }> {
  return post('/auth/forgot-password', { email })
}

export function resetPassword(token: string, password: string, confirmPassword: string): Promise<{ message: string }> {
  return post('/auth/reset-password', { token, password, confirm_password: confirmPassword })
}

export function verifyEmail(token: string): Promise<{ message: string }> {
  return post('/auth/verify-email', { token })
}

export function resendVerification(email: string): Promise<{ message: string }> {
  return post('/auth/resend-verification', { email })
}

export async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const makeRequest = () => fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: new Headers({
      ...Object.fromEntries(new Headers(init.headers).entries()),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    }),
    credentials: 'include',
  })
  let response = await makeRequest()
  if (response.status === 401) {
    const refreshed = await refreshSession()
    if (refreshed) response = await makeRequest()
  }
  return response
}

export function clearAuthentication(): void {
  clearToken()
}
