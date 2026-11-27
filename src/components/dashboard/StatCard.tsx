import { Activity, Camera, MessageCircle, MessageSquare, UserRoundPlus, Users, type LucideIcon } from 'lucide-react'

const icons: Record<string, LucideIcon> = { comments: MessageCircle, messages: MessageSquare, automations: Activity, success: Camera, leads: UserRoundPlus, accounts: Users }

export function StatCard({ label, value, change, trend, icon, demo = true }: { label: string; value: string; change: string; trend: 'up' | 'neutral'; icon: string; demo?: boolean }) {
  const Icon = icons[icon] ?? Activity
  return <article className="dashboard-stat-card">
    <div className="dashboard-stat-top"><span className="dashboard-stat-icon"><Icon size={18} /></span>{demo && <span className="dashboard-stat-demo">DEMO</span>}</div>
    <span className="dashboard-stat-label">{label}</span>
    <div className="dashboard-stat-bottom"><strong>{value}</strong><span className={`dashboard-stat-change ${trend}`}>{change}</span></div>
  </article>
}
