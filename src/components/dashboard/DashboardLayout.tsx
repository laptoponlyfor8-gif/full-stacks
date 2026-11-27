import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { useSocialAccounts } from '../../hooks/useSocialAccounts'
import { DashboardNavbar } from './DashboardNavbar'
import { DashboardSidebar } from './DashboardSidebar'

export function DashboardLayout() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [search, setSearch] = useState('')
  const { accounts } = useSocialAccounts()
  const connectedAccountCount = accounts.filter((account) => account.is_connected && account.connection_status === 'connected').length
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const profile = user ? {
    fullName: user.name,
    businessName: user.organization.name,
    email: user.email,
    mobile: '',
  } : null

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [location.pathname, location.search])
  return <div className={`dashboard-app${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
    <DashboardSidebar open={mobileSidebarOpen} collapsed={sidebarCollapsed} onClose={() => setMobileSidebarOpen(false)} onToggleCollapsed={() => setSidebarCollapsed(!sidebarCollapsed)} />
    <div className="dashboard-main-shell">
      <DashboardNavbar onMenuClick={() => setMobileSidebarOpen(true)} search={search} onSearchChange={setSearch} />
      <main className="dashboard-main-content"><Outlet context={{ search, profile, connectedAccountCount }} /></main>
      <footer className="dashboard-footer"><span>© 2026 DM Karo</span><span><i /> Demo workspace · Social accounts connect through Meta</span><button type="button" onClick={() => navigate('/dashboard/support')}>Help & support</button></footer>
    </div>
  </div>
}
