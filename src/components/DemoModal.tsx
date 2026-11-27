import { useEffect, useState } from 'react'
import { Check, MessageCircle, X } from 'lucide-react'

export function DemoModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [submitted, setSubmitted] = useState(false)
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])
  if (!open) return null

  const close = () => { setSubmitted(false); onClose() }
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close() }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="demo-title">
      <button className="modal-close" type="button" aria-label="Close dialog" onClick={close}><X /></button>
      <span className="modal-icon"><MessageCircle /></span>
      <h2 id="demo-title">See DM Karo in action</h2>
      <p className="modal-copy">Leave your details and our team will help you explore comment-to-DM automation.</p>
      {submitted ? <div className="modal-success"><Check size={17} /> Thanks. Your demo request is ready, and our team will be in touch.</div> : <form className="modal-form" onSubmit={(event) => { event.preventDefault(); setSubmitted(true) }}>
        <div className="modal-field"><label htmlFor="demo-name">Your name</label><input id="demo-name" name="name" autoComplete="name" required placeholder="Alex Morgan" /></div>
        <div className="modal-field"><label htmlFor="demo-email">Work email</label><input id="demo-email" name="email" type="email" autoComplete="email" required placeholder="alex@company.com" /></div>
        <button className="btn btn-primary" type="submit">Request a free demo</button>
      </form>}
    </section>
  </div>
}
