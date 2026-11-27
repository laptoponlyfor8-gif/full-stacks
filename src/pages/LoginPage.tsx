import { useState, type FormEvent } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { AuthFeedback } from '../components/AuthFeedback'
import { AuthFormField } from '../components/AuthFormField'
import { AuthLayout } from '../components/AuthLayout'
import { GoogleButton } from '../components/GoogleButton'
import { AuthApiError, resendVerification } from '../services/authApi'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [feedback, setFeedback] = useState({ message: '', kind: 'error' as 'error' | 'success' })
  const [errors, setErrors] = useState({ email: '', password: '' })
  const [verificationRequired, setVerificationRequired] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextErrors = {
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? '' : 'Enter a valid email address.',
      password: password ? '' : 'Enter your password.',
    }
    setErrors(nextErrors)
    if (nextErrors.email || nextErrors.password) return

    setFeedback({ message: '', kind: 'error' })
    setVerificationRequired(false)
    setLoading(true)
    try {
      await login(email.trim(), password, rememberMe)
      const state = location.state as { from?: { pathname?: string } } | null
      const destination = state?.from?.pathname
      navigate(destination?.startsWith('/') && !destination.startsWith('//') ? destination : '/dashboard', { replace: true })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Sign in could not be completed.'
      setFeedback({ message, kind: 'error' })
      setVerificationRequired(error instanceof AuthApiError && error.code === 'email_not_verified')
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async () => {
    setResending(true)
    try {
      const result = await resendVerification(email.trim())
      setFeedback({ message: result.message, kind: 'success' })
      setVerificationRequired(false)
    } catch (error) {
      setFeedback({ message: error instanceof Error ? error.message : 'Verification email could not be requested.', kind: 'error' })
    } finally {
      setResending(false)
    }
  }

  return <AuthLayout heading="Welcome back" description="Sign in to your DM Karo account.">
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <AuthFormField id="login-email" label="Email address" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(value) => setEmail(value)} error={errors.email} />
      <AuthFormField id="login-password" label="Password" type="password" autoComplete="current-password" placeholder="Enter your password" value={password} onChange={setPassword} error={errors.password} />
      <div className="auth-form-options"><label className="auth-checkbox"><input type="checkbox" checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} /><span>Remember me</span></label><Link to="/forgot-password">Forgot password?</Link></div>
      <AuthFeedback message={feedback.message} kind={feedback.kind} />
      {verificationRequired && <button className="auth-inline-action" type="button" disabled={resending} onClick={handleResendVerification}>{resending ? 'Requesting…' : 'Resend verification email'}</button>}
      <button className="btn btn-primary auth-submit" type="submit" disabled={loading}>{loading ? <><span className="auth-spinner" /> Signing in…</> : <>Login <ArrowRight size={16} /></>}</button>
    </form>
    <div className="auth-divider"><span>or</span></div>
    <GoogleButton />
    <p className="auth-switch">New to DM Karo? <Link to="/register">Create an account</Link></p>
  </AuthLayout>
}
