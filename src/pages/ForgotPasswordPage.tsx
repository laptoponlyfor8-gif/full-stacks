import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AuthFeedback } from '../components/AuthFeedback'
import { AuthFormField } from '../components/AuthFormField'
import { AuthLayout } from '../components/AuthLayout'
import { requestPasswordReset } from '../services/authApi'

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError('Enter a valid email address.')
      setMessage('')
      return
    }

    setError('')
    setLoading(true)
    try {
      const result = await requestPasswordReset(email.trim())
      setMessage(result.message)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'The request could not be completed.')
    } finally {
      setLoading(false)
    }
  }

  return <AuthLayout heading="Forgot your password?" description="Enter your email and we’ll send password reset instructions if an account matches.">
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <AuthFormField id="reset-email" label="Email address" type="email" autoComplete="email" placeholder="you@company.com" value={email} onChange={(value) => { setEmail(value); setError(''); setMessage('') }} error={error} />
      <AuthFeedback message={message} kind="success" />
      <button className="btn btn-primary auth-submit" type="submit" disabled={loading}>{loading ? <><span className="auth-spinner" /> Sending…</> : 'Send Reset Link'}</button>
    </form>
    <p className="auth-switch auth-forgot-back"><Link to="/login">Back to Login</Link></p>
  </AuthLayout>
}
