import { useState } from 'react'
import { ArrowLeft, ArrowRight, Camera, Check, LockKeyhole, ShieldCheck } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ConnectionStatusBadge } from '../components/dashboard/ConnectionStatusBadge'
import { useSocialAccounts } from '../hooks/useSocialAccounts'
import { startMetaConnection } from '../services/metaApi'
import type { SocialPlatform } from '../types'

const platformContent: Record<SocialPlatform, {
  title: string
  intro: string
  requirement: string
  permissions: string[]
}> = {
  instagram: {
    title: 'Connect Instagram',
    intro: 'Authorize an eligible Instagram Professional account using Business Login for Instagram.',
    requirement: 'Instagram Business or Creator accounts are supported; personal Instagram accounts are not. This flow does not require a linked Facebook Page.',
    permissions: ['instagram_business_basic to read the professional account ID and username'],
  },
  facebook: {
    title: 'Connect Facebook',
    intro: 'Authorize Facebook business assets and choose a Page returned by Meta.',
    requirement: 'The Facebook Login for Business configuration must grant the required Page listing access. Only Pages returned for your authorization can be selected.',
    permissions: ['Page access defined by your Facebook Login for Business configuration', 'Page ID and name for the Page you select'],
  },
}

export function SocialConnectionPage() {
  const { platform: routePlatform } = useParams()
  const platform: SocialPlatform = routePlatform === 'facebook' ? 'facebook' : 'instagram'
  const content = platformContent[platform]
  const navigate = useNavigate()
  const { accounts } = useSocialAccounts()
  const account = accounts.find((item) => item.platform === platform && item.is_connected)
    ?? accounts.find((item) => item.platform === platform)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState('')

  const handleConnect = async () => {
    setError('')
    setConnecting(true)
    try {
      const authorizationUrl = await startMetaConnection(platform)
      window.location.assign(authorizationUrl)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Meta authorization could not be started.')
      setConnecting(false)
    }
  }

  const status = !account
    ? 'Not Connected'
    : account.connection_status === 'connected'
      ? 'Connected'
      : account.connection_status === 'expired'
        ? 'Authorization Expired'
        : 'Disconnected'

  return <div className="dashboard-page-content social-connection-page">
    <Link className="social-back-link" to="/dashboard/accounts"><ArrowLeft size={15} /> Back to connected accounts</Link>
    <div className="social-connect-hero">
      <div className={`social-connect-platform-icon ${platform}`}>{platform === 'instagram' ? <Camera size={25} /> : <span>f</span>}</div>
      <span className="dashboard-page-eyebrow">OFFICIAL META AUTHORIZATION</span>
      <h1>{content.title}</h1>
      <p>{content.intro}</p>
      <ConnectionStatusBadge status={status} />
    </div>
    <div className="social-connect-grid">
      <section className="dashboard-panel social-requirements-panel">
        <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">BEFORE YOU CONNECT</span><h2>Requirements</h2></div><ShieldCheck size={18} /></div>
        <div className="social-requirement-callout"><LockKeyhole size={17} /><span>{content.requirement}</span></div>
        <div className="social-permissions"><h3>This connection requests or uses:</h3>{content.permissions.map((permission) => <p key={permission}><Check size={15} />{permission}</p>)}</div>
        <p className="social-privacy-notice"><ShieldCheck size={15} /> Meta handles sign-in. DM Karo never requests or stores your Instagram or Facebook password. Tokens are encrypted by the backend and are not sent back to this page.</p>
      </section>
      <section className="social-demo-auth-panel">
        <span className="social-demo-panel-icon"><ShieldCheck size={20} /></span>
        <span className="social-demo-label">SECURE OAUTH · META HOSTED LOGIN</span>
        <h2>{status === 'Connected' ? 'Account authorized' : 'Continue to Meta'}</h2>
        <p>{status === 'Connected' && account ? `${account.account_name} is connected to this organization.` : 'You will leave DM Karo and authorize the requested access directly with Meta.'}</p>
        {error && <p className="social-connect-error" role="alert">{error}</p>}
        {status === 'Connected' && <button className="btn btn-secondary social-connect-cta" type="button" onClick={() => navigate('/dashboard/accounts')}>View account management <ArrowRight size={15} /></button>}
        {status !== 'Connected' && <button className="btn btn-primary social-connect-cta" type="button" onClick={() => void handleConnect()} disabled={connecting}>{platform === 'instagram' ? <Camera size={16} /> : <span className="social-f-icon">f</span>} {connecting ? 'Opening Meta…' : `Continue with ${platform === 'instagram' ? 'Instagram' : 'Facebook'}`} <ArrowRight size={15} /></button>}
      </section>
    </div>
    <p className="social-production-note"><strong>Meta availability:</strong> A successful authorization depends on your Meta app type, enabled products, granted permissions, test-user eligibility, and App Review/Advanced Access status. Account connection alone does not enable messaging or automation.</p>
  </div>
}
