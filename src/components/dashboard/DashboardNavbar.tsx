import { useState } from 'react'
import { Bell, ChevronDown, CircleHelp, LogOut, Menu, Search, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'

export function DashboardNavbar({ onMenuClick, search, onSearchChange }: { onMenuClick: () => void; search: string; onSearchChange: (value: string) => void }) {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [profileOpen, setProfileOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [logoutError, setLogoutError] = useState('')
  const fullName = user?.name || 'Account'
  const initials = fullName.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()

  const handleLogout = async () => {
    setLogoutError('')
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (error) {
      setLogoutError(error instanceof Error ? error.message : 'Log out could not be completed. Please try again.')
    }
  }

  return <header className="dashboard-topbar">
    <button className="dashboard-menu-toggle" type="button" aria-label="Open navigation" onClick={onMenuClick}><Menu size={20} /></button>
    <label className="dashboard-search"><Search size={17} /><input value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Search automations, leads..." aria-label="Search demo dashboard records" /><kbd>⌘ K</kbd></label>
    <div className="dashboard-topbar-actions">
      <div className="dashboard-popover-anchor"><button className="dashboard-icon-button" type="button" aria-label="Notifications" aria-expanded={notificationsOpen} onClick={() => { setNotificationsOpen(!notificationsOpen); setProfileOpen(false) }}><Bell size={18} /><i /></button>
        {notificationsOpen && <div className="dashboard-popover notification-popover"><strong>Notifications</strong><p>You’re all caught up.</p><span>Demo notifications will appear here.</span></div>}
      </div>
      <button className="dashboard-icon-button help-button" type="button" aria-label="Help and support" onClick={() => navigate('/dashboard/support')}><CircleHelp size={18} /></button>
      <div className="dashboard-popover-anchor">
        <button className="dashboard-profile-button" type="button" aria-expanded={profileOpen} onClick={() => { setProfileOpen(!profileOpen); setNotificationsOpen(false) }}>
          <span className="dashboard-avatar">{initials || <UserRound size={15} />}</span><span className="dashboard-profile-name">{fullName}</span><ChevronDown size={15} />
        </button>
        {profileOpen && <div className="dashboard-popover profile-popover"><div className="profile-popover-user"><strong>{fullName}</strong><span>{user?.email}</span><em>{user?.organization.role.toUpperCase()}</em></div>{logoutError && <p role="alert">{logoutError}</p>}<button type="button" onClick={handleLogout}><LogOut size={15} /> Log out</button></div>}
      </div>
    </div>
  </header>
}
