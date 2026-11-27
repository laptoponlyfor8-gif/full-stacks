import {
  Activity, Bot, Camera, ChartNoAxesCombined, CircleHelp, CreditCard, FileImage, Inbox,
  ContactRound, LayoutDashboard, MessageCircle, MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, Settings, Users, Workflow, X,
} from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { Brand } from '../SiteNav'
import type { DashboardNavItem } from '../../types'
import { useSocialAccounts } from '../../hooks/useSocialAccounts'

const navigation: DashboardNavItem[] = [
  { label: 'Overview', path: '/dashboard', icon: LayoutDashboard, section: 'workspace' },
  { label: 'Create Automation', path: '/dashboard/automations/create', icon: Plus, section: 'workspace' },
  { label: 'My Automations', path: '/dashboard/automations', icon: Workflow, section: 'workspace' },
  { label: 'Connected Accounts', path: '/dashboard/accounts', icon: Activity, section: 'workspace' },
  { label: 'Instagram Comments', path: '/dashboard/comments?platform=instagram', icon: Camera, section: 'manage' },
  { label: 'Facebook Comments', path: '/dashboard/comments?platform=facebook', icon: MessageCircle, section: 'manage' },
  { label: 'DM Messages', path: '/dashboard/messages', icon: MessageSquare, section: 'manage' },
  { label: 'Unified Inbox', path: '/dashboard/inbox', icon: Inbox, section: 'manage' },
  { label: 'Contacts', path: '/dashboard/contacts', icon: ContactRound, section: 'manage' },
  { label: 'Leads', path: '/dashboard/leads', icon: Users, section: 'manage' },
  { label: 'Analytics', path: '/dashboard/analytics', icon: ChartNoAxesCombined, section: 'manage' },
  { label: 'AI Assistant', path: '/dashboard/ai-assistant', icon: Bot, section: 'manage' },
  { label: 'Billing', path: '/dashboard/billing', icon: CreditCard, section: 'manage' },
  { label: 'Media Library', path: '/dashboard/media', icon: FileImage, section: 'manage' },
  { label: 'Settings', path: '/dashboard/settings', icon: Settings, section: 'manage' },
  { label: 'Help & Support', path: '/dashboard/support', icon: CircleHelp, section: 'manage' },
]

export function DashboardSidebar({ open, collapsed, onClose, onToggleCollapsed }: { open: boolean; collapsed: boolean; onClose: () => void; onToggleCollapsed: () => void }) {
  const location = useLocation()
  const { accounts } = useSocialAccounts()
  const connectedCount = accounts.filter((account) => account.is_connected && account.connection_status === 'connected').length
  const renderLinks = (section: DashboardNavItem['section']) => navigation.filter((item) => item.section === section).map(({ label, path, icon: Icon }) => (
    <NavLink
      key={label}
      to={path}
      end
      title={collapsed ? label : undefined}
      className={({ isActive }) => {
        const [itemPath, query] = path.split('?')
        const platformMatch = itemPath !== '/dashboard/comments' || (query ? new URLSearchParams(location.search).get('platform') === query.split('=')[1] : !location.search.includes('platform='))
        return `dashboard-nav-link${isActive && platformMatch ? ' active' : ''}`
      }}
      onClick={onClose}
    >
      <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{label === 'Connected Accounts' && <i className="dashboard-account-count">{connectedCount}</i>}
    </NavLink>
  ))

  return <>
    {open && <button className="dashboard-overlay" type="button" aria-label="Close navigation overlay" onClick={onClose} />}
    <aside className={`dashboard-sidebar${open ? ' mobile-open' : ''}${collapsed ? ' collapsed' : ''}`}>
      <div className="dashboard-sidebar-brand"><Brand /><button className="dashboard-sidebar-close" type="button" aria-label="Close navigation" onClick={onClose}><X size={18} /></button></div>
      <div className="dashboard-sidebar-caption">WORKSPACE</div>
      <nav className="dashboard-sidebar-nav" aria-label="Dashboard navigation">
        {renderLinks('workspace')}
        <div className="dashboard-sidebar-caption manage-caption">MANAGE</div>
        {renderLinks('manage')}
      </nav>
      <div className="dashboard-sidebar-foot">
        <span className="dashboard-sidebar-help-icon"><MessageCircle size={17} /></span>
        <div><strong>Need a hand?</strong><span>We’re here to help</span></div>
        <NavLink to="/dashboard/support" aria-label="Get support"><CircleHelp size={16} /></NavLink>
      </div>
      <button className="dashboard-collapse-button" type="button" onClick={onToggleCollapsed} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}</button>
    </aside>
  </>
}
