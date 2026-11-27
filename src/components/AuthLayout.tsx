import type { ReactNode } from 'react'
import { ArrowLeft, MessageCircle, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from './SiteNav'

export function AuthLayout({ children, heading, description }: { children: ReactNode; heading: string; description: string }) {
  return <main className="auth-page">
    <section className="auth-story" aria-label="About DM Karo">
      <Brand />
      <div className="auth-story-content">
        <span className="auth-story-kicker"><Sparkles size={14} /> CONVERSATIONS THAT CONVERT</span>
        <h1>Make every conversation count.</h1>
        <p>Bring your social conversations together and make it easier to build lasting customer relationships.</p>
        <div className="auth-story-card"><span className="auth-story-icon"><MessageCircle /></span><span><strong>Good to see you here</strong><small>Your secure DM Karo workspace is just a few steps away.</small></span></div>
      </div>
      <span className="auth-story-footer">A smarter way to connect with your audience.</span>
    </section>
    <section className="auth-panel">
      <div className="auth-mobile-brand"><Brand /></div>
      <div className="auth-card">
        <div className="auth-card-heading"><h2>{heading}</h2><p>{description}</p></div>
        {children}
        <Link className="auth-back-home" to="/"><ArrowLeft size={15} /> Back to Home</Link>
        <p className="auth-demo-note">Your account is protected with secure authentication.</p>
      </div>
    </section>
  </main>
}
