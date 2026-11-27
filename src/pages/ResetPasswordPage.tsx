import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AuthFeedback } from '../components/AuthFeedback'
import { AuthFormField } from '../components/AuthFormField'
import { AuthLayout } from '../components/AuthLayout'
import { resetPassword } from '../services/authApi'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!token) {
      setError('This password reset link is incomplete.')
      return
    }
    if (password.length < 8 || password.length > 128) {
      setError('Use a password between 8 and 128 characters.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setError('')
    setLoading(true)
    try {
      const result = await resetPassword(token, password, confirmPassword)
      setMessage(result.message)
      setPassword('')
      setConfirmPassword('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Your password could not be reset.')
    } finally {
      setLoading(false)
    }
  }

  return <AuthLayout heading="Choose a new password" description="Reset links are single-use and expire for your security.">
    <form className="auth-form" onSubmit={handleSubmit} noValidate>
      <AuthFormField id="new-password" label="New password" type="password" autoComplete="new-password" placeholder="At least 8 characters" value={password} onChange={(value) => { setPassword(value); setError('') }} error="" minLength={8} />
      <AuthFormField id="confirm-new-password" label="Confirm new password" type="password" autoComplete="new-password" placeholder="Repeat your password" value={confirmPassword} onChange={(value) => { setConfirmPassword(value); setError('') }} error="" />
      <AuthFeedback message={error} kind="error" />
      <AuthFeedback message={message} kind="success" />
      <button className="btn btn-primary auth-submit" type="submit" disabled={loading || Boolean(message)}>{loading ? <><span className="auth-spinner" /> Updating…</> : 'Reset Password'}</button>
    </form>
    <p className="auth-switch auth-forgot-back"><Link to="/login">Back to Login</Link></p>
  </AuthLayout>
}
