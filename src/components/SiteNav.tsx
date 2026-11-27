import { useState } from 'react'
import { ArrowUpRight, Menu, MessageCircle, X } from 'lucide-react'
import { Link } from 'react-router-dom'

const links = [
  ['Home', '#home'],
  ['Features', '#features'],
  ['How it works', '#how-it-works'],
  ['Pricing', '#pricing'],
  ['FAQ', '#faq'],
]

export function Brand() {
  return <Link className="brand" to="/" aria-label="DM Karo home"><span className="brand-mark"><MessageCircle /></span><span>DM Karo</span></Link>
}

export function SiteNav() {
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  return <header className="navbar">
    <div className="container nav-inner">
      <Brand />
      <nav className="nav-links" aria-label="Main navigation">{links.map(([label, href]) => <a key={href} href={href}>{label}</a>)}</nav>
      <div className="nav-actions"><Link className="nav-login" to="/login">Login</Link><Link className="btn btn-primary" to="/register">Get Started <ArrowUpRight size={15} /></Link></div>
      <button className="menu-toggle" type="button" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
    </div>
    {menuOpen && <nav className="mobile-panel" aria-label="Mobile navigation">{links.map(([label, href]) => <a key={href} href={href} onClick={closeMenu}>{label}</a>)}<Link to="/login" onClick={closeMenu}>Login</Link><Link className="btn btn-primary" to="/register" onClick={closeMenu}>Get Started <ArrowUpRight size={15} /></Link></nav>}
  </header>
}
