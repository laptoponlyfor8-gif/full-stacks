import { useState } from 'react'
import { AuthFeedback } from './AuthFeedback'

export function GoogleButton() {
  const [message, setMessage] = useState('')
  return <div className="auth-google-wrap">
    <button className="auth-google-button" type="button" onClick={() => setMessage('Google sign-in is not configured yet.')}>
      <span className="google-g" aria-hidden="true">G</span> Continue with Google
    </button>
    <AuthFeedback message={message} kind="error" />
  </div>
}
