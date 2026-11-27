import { ArrowUpRight, Camera, MessageCircle, MessageSquare, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'

const actions = [
  { label: 'Create New Automation', detail: 'Start a comment-to-DM workflow', path: '/dashboard/automations/create', icon: Plus, primary: true },
  { label: 'Connect Instagram', detail: 'Try the Instagram demo connection', path: '/dashboard/accounts/instagram', icon: Camera },
  { label: 'Connect Facebook', detail: 'Try the Facebook demo connection', path: '/dashboard/accounts/facebook', icon: MessageCircle },
  { label: 'View Inbox', detail: 'Browse sample conversations', path: '/dashboard/inbox', icon: MessageSquare },
]

export function QuickActions() {
  return <section className="dashboard-quick-actions">
    <div className="dashboard-section-title-row"><div><span className="dashboard-section-kicker">GET STARTED</span><h2>Quick Actions</h2></div><span className="quick-actions-demo">DEMO WORKSPACE</span></div>
    <div className="quick-action-grid">{actions.map(({ label, detail, path, icon: Icon, primary }) => <Link className={`quick-action-card${primary ? ' primary' : ''}`} key={label} to={path}><span className="quick-action-icon"><Icon size={17} /></span><span className="quick-action-copy"><strong>{label}</strong><small>{detail}</small></span><ArrowUpRight className="quick-action-arrow" size={15} /></Link>)}</div>
  </section>
}
