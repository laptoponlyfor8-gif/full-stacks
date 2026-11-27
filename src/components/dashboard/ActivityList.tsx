import { ArrowUpRight, MessageCircle, MessageSquare, Sparkles, UserRoundPlus } from 'lucide-react'
import type { DemoActivity } from '../../types'

const activityIcons = { comment: MessageCircle, message: MessageSquare, lead: UserRoundPlus, automation: Sparkles }

export function ActivityList({ activities, search = '' }: { activities: DemoActivity[]; search?: string }) {
  const filtered = activities.filter((activity) => `${activity.title} ${activity.detail}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="dashboard-panel activity-panel">
    <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">LATEST UPDATES</span><h2>Recent Activity</h2></div><span className="dashboard-live-dot"><i /> DEMO</span></div>
    <div className="dashboard-activity-list">{filtered.length ? filtered.map((activity) => { const Icon = activityIcons[activity.kind]; return <article className="dashboard-activity-item" key={activity.id}><span className={`dashboard-activity-icon ${activity.kind}`}><Icon size={16} /></span><div><strong>{activity.title}</strong><p>{activity.detail}</p></div><time>{activity.time}</time></article> }) : <p className="dashboard-empty-state">No demo activity matches your search.</p>}</div>
    <button className="dashboard-activity-footer" type="button">View activity log <ArrowUpRight size={14} /></button>
  </section>
}
