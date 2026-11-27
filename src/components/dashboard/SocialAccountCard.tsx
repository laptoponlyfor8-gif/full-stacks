import { ArrowRight, Camera, MessageCircle, RefreshCw, ShieldCheck, Unplug } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { SocialAccount, SocialPlatform } from '../../types'
import { ConnectionStatusBadge } from './ConnectionStatusBadge'

const platformDetails: Record<SocialPlatform, { title: string; description: string; types: string; path: string }> = {
  instagram: {
    title: 'Instagram',
    description: 'Connect an eligible Instagram Professional account using Instagram Login.',
    types: 'Business and Creator accounts; personal accounts are not supported',
    path: '/dashboard/accounts/instagram',
  },
  facebook: {
    title: 'Facebook',
    description: 'Select a Facebook Page that you are authorized to manage.',
    types: 'Pages returned by Facebook Login for Business',
    path: '/dashboard/accounts/facebook',
  },
}

export function SocialAccountCard({ platform, account, onDisconnect }: { platform: SocialPlatform; account: SocialAccount | null; onDisconnect: (account: SocialAccount) => void }) {
  const details = platformDetails[platform]
  const connected = account?.connectionStatus === 'Connected'
  const Logo = platform === 'instagram' ? Camera : MessageCircle
  const isReconnect = account?.connectionStatus === 'Authorization Expired' || account?.connectionStatus === 'Connection Error'

  return <article className={`social-integration-card ${platform}`}>
    <div className={`social-integration-logo ${platform}`}>{platform === 'instagram' ? <Logo size={23} /> : <span>f</span>}</div>
    <div className="social-integration-heading"><div><h2>{details.title}</h2><p>{details.description}</p></div><ConnectionStatusBadge status={account?.connectionStatus ?? 'Not Connected'} /></div>
    <div className="social-integration-type"><ShieldCheck size={15} /><span>Supports {details.types}</span></div>
    {connected && account && <div className="social-connected-identity"><span className={`social-account-avatar ${platform}`}>{account.profileImage ? <img src={account.profileImage} alt="" /> : platform === 'instagram' ? <Camera size={17} /> : account.accountName.slice(0, 1)}</span><span><strong>{account.accountName}</strong><small>{account.accountType}</small></span><span className="social-demo-chip">META</span></div>}
    <p className="social-integration-disclaimer">{connected ? 'Authorized account connected to this organization.' : 'Continue to Meta to authorize access. DM Karo never asks for your social account password.'}</p>
    <div className="social-integration-actions">
      {connected && account ? <>
        <Link className="social-manage-link" to={details.path}>Connection details <ArrowRight size={14} /></Link>
        <button className="social-disconnect-button" type="button" onClick={() => onDisconnect(account)}><Unplug size={15} /> Disconnect</button>
      </> : <>
        <Link className="btn btn-primary" to={details.path}>{isReconnect ? <RefreshCw size={15} /> : <Logo size={16} />}{isReconnect ? `Reconnect ${details.title}` : `Connect ${details.title}`}</Link>
        <span className="social-connect-note">No password required</span>
      </>}
    </div>
  </article>
}
