import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../components/SiteNav'

type Mode = 'login' | 'signup' | 'privacy' | 'terms' | 'not-found'

export function PlaceholderPage({ mode }: { mode: Mode }) {
  const title = mode === 'login' ? 'Login is coming soon' : mode === 'signup' ? 'Your growth starts here' : mode === 'privacy' ? 'Privacy policy preview' : mode === 'terms' ? 'Terms preview' : 'We could not find that page'
  const copy = mode === 'not-found' ? 'That page is not part of this preview. Head back to the DM Karo landing page.' : mode === 'privacy' || mode === 'terms' ? 'This page is a placeholder in the landing-page preview. Legal content has not been published.' : 'This is a frontend preview. Account access is not available yet.'
  return <main className="placeholder-page"><section className="placeholder-box"><Brand /><h1>{title}</h1><p>{copy}</p><Link className="btn btn-primary" to="/"><ArrowLeft size={16} /> Back to home</Link></section></main>
}
