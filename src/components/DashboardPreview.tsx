import { Activity, ArrowUpRight, BarChart3, Bell, Camera, Check, ChevronDown, CircleHelp, LayoutDashboard, MessageCircle, MessageSquare, MoreHorizontal, Settings, Sparkles, Users } from 'lucide-react'
import type { ReactNode } from 'react'

function Stat({ icon, label, value, change }: { icon: ReactNode; label: string; value: string; change: string }) {
  return <div className="stat-card"><span className="stat-label">{icon}{label}</span><strong className="stat-value">{value}<span className="stat-change">{change}</span></strong></div>
}

export function DashboardPreview() {
  return <div className="dashboard-wrap" aria-label="Preview of the DM Karo automation dashboard">
    <div className="dashboard-glow" />
    <div className="float-note two"><span className="float-icon"><Camera /></span><span className="float-copy"><b>New comment detected</b><span>Just now - Instagram Reel</span></span></div>
    <div className="dashboard">
      <div className="dash-topbar"><div className="dash-brand"><span className="dash-logo"><MessageCircle /></span> DM Karo <ChevronDown size={11} /></div><div className="dash-top-actions"><Bell size={13} /><CircleHelp size={13} /><span className="dash-profile" /></div></div>
      <div className="dash-content"><aside className="dash-sidebar"><div className="dash-menu-item active"><LayoutDashboard />Overview</div><div className="dash-menu-item"><Activity />Automations</div><div className="dash-menu-item"><MessageSquare />Inbox</div><div className="dash-menu-item"><Users />Contacts</div><div className="dash-menu-item"><BarChart3 />Analytics</div><div className="dash-menu-item"><Settings />Settings</div></aside>
        <main className="dash-main"><div className="dash-heading-row"><div><h2 className="dash-title">Good morning, Alex</h2><p className="dash-subtitle">Here is what is happening with your conversations.</p></div><span className="live-pill"><i />All systems live</span></div>
          <div className="stats-grid"><Stat icon={<MessageCircle />} label="Total comments" value="2,481" change="+18%" /><Stat icon={<MessageSquare />} label="Messages sent" value="1,936" change="+24%" /><Stat icon={<Users />} label="New leads" value="328" change="+12%" /></div>
          <div className="dash-lower"><section className="preview-card"><div className="preview-card-head">Recent comment <span>View all <ArrowUpRight size={9} /></span></div><div className="comment-preview"><span className="mini-avatar" /><div className="comment-text"><b>@sarah.creates <Camera className="ig-icon" size={8} /></b>This is exactly what I need! How do I get started?</div></div><div className="dm-sent">Comment trigger <Check /></div></section>
            <section className="preview-card"><div className="preview-card-head">Automatic DM <span>Preview</span></div><div className="dm-bubble">Hey Sarah! Thanks for your interest. Tap below and we'll send you the details.</div><div className="dm-sent">Sent automatically <Check /></div></section></div>
          <div className="automation-card"><span className="automation-icon"><Sparkles /></span><span className="automation-info"><b>Reel comment → Welcome DM</b><span>Instagram · Updated 2 hours ago</span></span><span className="toggle-on" aria-label="Automation active" /><MoreHorizontal size={13} /></div>
        </main></div>
    </div>
    <div className="float-note one"><span className="float-icon blue"><Check /></span><span className="float-copy"><b>Automation active</b><span>1,936 messages sent this month</span></span></div>
  </div>
}
