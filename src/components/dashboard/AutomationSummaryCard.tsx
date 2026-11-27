import { ArrowUpRight, Camera, MessageCircle } from 'lucide-react'
import type { AutomationFields } from '../../utils/automationValidation'

export function AutomationSummaryCard({ fields, accountName }: { fields: AutomationFields; accountName: string }) {
  return <section className="automation-summary-card">
    <div className="automation-summary-header"><div><span className="dashboard-section-kicker">REVIEW YOUR SETUP</span><h2>Automation summary</h2></div><span className="automation-summary-demo">BACKEND DRAFT</span></div>
    <dl>
      <div><dt>Automation name</dt><dd>{fields.name.trim() || 'Not set'}</dd></div>
      <div><dt>Platform</dt><dd>{fields.platform ? <><span className={`platform-label ${fields.platform.toLowerCase()}`}>{fields.platform === 'Instagram' ? <Camera size={13} /> : <MessageCircle size={13} />}{fields.platform}</span></> : 'Not selected'}</dd></div>
      <div><dt>Social account</dt><dd>{accountName || 'Not selected'}</dd></div>
      <div><dt>Content type</dt><dd>{fields.contentType || 'Not selected'}</dd></div>
      <div className="summary-url"><dt>Reel / Post URL</dt><dd>{fields.postUrl || 'Not added'}</dd></div>
    </dl>
    <p><ArrowUpRight size={13} /> The backend will verify the permalink using the selected connected account before saving.</p>
  </section>
}
