import { CircleAlert, CircleCheck } from 'lucide-react'

export function AuthFeedback({ message, kind }: { message: string; kind: 'success' | 'error' }) {
  if (!message) return null
  const Icon = kind === 'success' ? CircleCheck : CircleAlert
  return <div className={`auth-feedback ${kind}`} role={kind === 'error' ? 'alert' : 'status'}><Icon size={17} /><span>{message}</span></div>
}
