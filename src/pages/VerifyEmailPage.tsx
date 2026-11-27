import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AuthFeedback } from '../components/AuthFeedback'
import { AuthLayout } from '../components/AuthLayout'
import { verifyEmail } from '../services/authApi'

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(token ? '' : 'This verification link is incomplete.')
  const [message, setMessage] = useState('')

  const handleVerify = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await verifyEmail(token)
      setMessage(result.message)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Your email could not be verified.')
    } finally {
      setLoading(false)
    }
  }

  return <AuthLayout heading="Verify your email" description="Confirm your email address to activate your DM Karo account.">
    <div className="auth-form">
      <AuthFeedback message={error} kind="error" />
      <AuthFeedback message={message} kind="success" />
      {!message && token && <button className="btn btn-primary auth-submit" type="button" disabled={loading} onClick={handleVerify}>{loading ? <><span className="auth-spinner" /> Verifying…</> : 'Verify Email Address'}</button>}
      {message && <p className="auth-switch"><Link to="/login">Continue to Login</Link></p>}
    </div>
  </AuthLayout>
}
