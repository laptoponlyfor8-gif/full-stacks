import type { ConnectionStatus } from '../../types'

export function ConnectionStatusBadge({ status }: { status: ConnectionStatus }) {
  const className = status === 'Connected'
    ? 'connected'
    : status === 'Expired'
      ? 'authorization-expired'
      : status.toLowerCase().replaceAll(/[^a-z]+/g, '-').replace(/^-|-$/g, '')
  return <span className={`connection-status-badge ${className}`}><i />{status}</span>
}
