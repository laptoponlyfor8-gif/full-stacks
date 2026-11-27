import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from './SiteNav'

const currentYear = new Date().getFullYear()

export function SiteFooter() {
  return <footer className="footer"><div className="container"><div className="footer-main"><div className="footer-brand-block"><Brand /><p className="footer-brand-copy">Automate conversations that build real customer connections. Automate. Connect. Grow.</p></div>
    <div><h3>Product</h3><nav className="footer-links"><a href="#features">Features</a><a href="#how-it-works">How it works</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a></nav></div>
    <div><h3>Features</h3><nav className="footer-links"><a href="#features">Instagram automation</a><a href="#features">Lead generation</a><a href="#features">Unified inbox</a><a href="#features">Analytics</a></nav></div>
    <div><h3>Get in touch</h3><nav className="footer-links"><a href="mailto:hello@dmkaro.com">Contact <ArrowUpRight size={12} /></a><Link to="/privacy">Privacy Policy</Link><Link to="/terms">Terms and Conditions</Link></nav></div></div>
    <div className="footer-bottom"><span>© {currentYear} DM Karo. All rights reserved.</span><span className="footer-bottom-links"><Link to="/privacy">Privacy Policy</Link><Link to="/terms">Terms and Conditions</Link></span></div></div></footer>
}
