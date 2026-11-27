import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { DashboardLayout } from './components/dashboard/DashboardLayout'
import { DashboardOverviewPage } from './pages/DashboardOverviewPage'
import { DashboardModulePage } from './pages/DashboardModulePage'
import { SocialAccountsPage } from './pages/SocialAccountsPage'
import { SocialConnectionPage } from './pages/SocialConnectionPage'
import { CreateAutomationPage } from './pages/CreateAutomationPage'
import { AutomationsPage } from './pages/AutomationsPage'
import { AutomationDetailPage } from './pages/AutomationDetailPage'
import { ConfigureAutomationPage } from './pages/ConfigureAutomationPage'
import { MessageBuilderPage } from './pages/MessageBuilderPage'
import { ProtectedRoute, PublicOnlyRoute } from './components/ProtectedRoute'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
import { AIAssistantPage } from './pages/AIAssistantPage'
import { InboxPage } from './pages/InboxPage'
import { ContactsPage } from './pages/ContactsPage'
import { LeadsPage } from './pages/LeadsPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { BillingPage } from './pages/BillingPage'

function App() {
  const location = useLocation()
  return <Routes>
    <Route path="/" element={<HomePage />} />
    <Route path="/login" element={<PublicOnlyRoute><LoginPage /></PublicOnlyRoute>} />
    <Route path="/register" element={<PublicOnlyRoute><RegisterPage /></PublicOnlyRoute>} />
    <Route path="/forgot-password" element={<PublicOnlyRoute><ForgotPasswordPage /></PublicOnlyRoute>} />
    <Route path="/reset-password" element={<ResetPasswordPage />} />
    <Route path="/verify-email" element={<VerifyEmailPage />} />
    <Route path="/dashboard" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
      <Route index element={<DashboardOverviewPage />} />
      <Route path="automations" element={<AutomationsPage />} />
      <Route path="automations/create" element={<CreateAutomationPage />} />
      <Route path="automations/configure" element={<ConfigureAutomationPage key={location.search} />} />
      <Route path="automations/message-builder" element={<MessageBuilderPage />} />
      <Route path="automations/:id" element={<AutomationDetailPage />} />
      <Route path="accounts" element={<SocialAccountsPage />} />
      <Route path="accounts/:platform" element={<SocialConnectionPage />} />
      <Route path="comments" element={<DashboardModulePage />} />
      <Route path="messages" element={<DashboardModulePage />} />
      <Route path="inbox" element={<InboxPage />} />
      <Route path="contacts" element={<ContactsPage />} />
      <Route path="leads" element={<LeadsPage />} />
      <Route path="analytics" element={<AnalyticsPage />} />
      <Route path="billing" element={<BillingPage />} />
      <Route path="ai-assistant" element={<AIAssistantPage />} />
      <Route path="media" element={<DashboardModulePage />} />
      <Route path="settings" element={<DashboardModulePage />} />
      <Route path="support" element={<DashboardModulePage />} />
    </Route>
    <Route path="/get-started" element={<Navigate to="/register" replace />} />
    <Route path="/privacy" element={<PlaceholderPage mode="privacy" />} />
    <Route path="/terms" element={<PlaceholderPage mode="terms" />} />
    <Route path="*" element={<PlaceholderPage mode="not-found" />} />
  </Routes>
}

export default App
