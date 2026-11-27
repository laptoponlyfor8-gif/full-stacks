import { useEffect, useState } from 'react'
import { AlertCircle, ArrowLeft, BellRing, Check, MessageCircleReply, Send, ShieldCheck, Sparkles } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { KeywordMatchMethodPicker } from '../components/dashboard/KeywordMatchMethodPicker'
import { KeywordTagEditor } from '../components/dashboard/KeywordTagEditor'
import { automationConfiguration, getAutomation, updateAutomation } from '../services/automationsApi'
import { askAIAssist } from '../services/aiApi'
import type { Automation, KeywordMatchMethod } from '../types'

export function ConfigureAutomationPage() {
  const [searchParams] = useSearchParams()
  const automationId = searchParams.get('id')
  const [automation, setAutomation] = useState<Automation | null>(null)
  const [keywords, setKeywords] = useState<string[]>([])
  const [method, setMethod] = useState<KeywordMatchMethod>('contains')
  const [privateReply, setPrivateReply] = useState('')
  const [publicReplyEnabled, setPublicReplyEnabled] = useState(false)
  const [publicReply, setPublicReply] = useState('')
  const [loading, setLoading] = useState(Boolean(automationId))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [aiTarget, setAiTarget] = useState('')

  useEffect(() => {
    if (!automationId) {
      return
    }
    let active = true
    getAutomation(automationId)
      .then((record) => {
        if (!active) return
        setAutomation(record)
        setKeywords(record.commentTrigger?.keywords ?? [])
        setMethod(record.commentTrigger?.matchingMethod ?? 'contains')
        setPrivateReply(record.privateReplyText ?? '')
        setPublicReplyEnabled(record.commentTrigger?.publicReplyEnabled ?? false)
        setPublicReply(record.commentTrigger?.customPublicReply ?? '')
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Could not load this automation.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [automationId])

  const generateAutomationSuggestion = async (target: 'keywords' | 'private' | 'public') => {
    if (!automation) return
    setAiTarget(target)
    setError('')
    setNotice('')
    try {
      const context = [
        `Automation: ${automation.name}`,
        `Platform: ${automation.platform}`,
        `Trigger: ${automation.triggerType}`,
        `Content type: ${automation.contentType}`,
        `Existing keywords: ${keywords.join(', ') || 'none'}`,
      ].join('\n')
      const action = target === 'keywords' ? 'suggest_keywords' : target === 'public' ? 'public_reply' : 'draft_message'
      const inputText = target === 'keywords'
        ? `Suggest relevant trigger keywords for this automation: ${automation.name}`
        : target === 'public'
          ? 'Draft a short public reply that acknowledges the comment and invites a helpful next step.'
          : 'Draft a brief private message that responds to a matching comment and offers useful next information.'
      const response = await askAIAssist(action, inputText, context)
      if (target === 'keywords') {
        const suggestions = response.result
          .split(/[\n,]+/)
          .map((item) => item.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '').trim())
          .filter(Boolean)
        const seen = new Set(keywords.map((item) => item.trim().toLocaleLowerCase()))
        const additions = suggestions.filter((item) => {
          const key = item.toLocaleLowerCase()
          if (seen.has(key)) return false
          seen.add(key)
          return true
        }).slice(0, 10)
        setKeywords((current) => [...current, ...additions])
        setNotice('AI keyword suggestions added. Review and edit the keyword list before saving.')
      } else if (target === 'public') {
        setPublicReply(response.result)
        setNotice('AI public reply draft added. Review and edit it before saving.')
      } else {
        setPrivateReply(response.result)
        setNotice('AI private reply draft added. Review and edit it before saving.')
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not generate an AI suggestion.')
    } finally {
      setAiTarget('')
    }
  }

  const save = async () => {
    if (!automationId) return
    if (!keywords.some((keyword) => keyword.trim())) {
      setError('Add at least one keyword or phrase.')
      return
    }
    if (publicReplyEnabled && !publicReply.trim()) {
      setError('Enter the public reply text or disable public replies.')
      return
    }
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const updated = await updateAutomation(
        automationId,
        automationConfiguration(
          keywords.map((keyword) => keyword.trim()).filter(Boolean),
          method,
          privateReply,
          publicReplyEnabled,
          publicReply,
        ),
      )
      setAutomation(updated)
      setNotice('Automation configuration saved. Activate it from My Automations when ready.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this configuration.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="dashboard-page-content" role="status">Loading automation configuration…</div>
  if (!automationId) return <div className="dashboard-page-content keyword-config-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">AUTOMATIONS · CONFIGURATION</span><h1>Configure Automation</h1></div></div>
    <div className="automation-feedback error" role="alert">Choose an automation before configuring its triggers.</div>
    <Link className="automation-back-button" to="/dashboard/automations"><ArrowLeft size={14} /> Back to My Automations</Link>
  </div>
  if (!automation) return <div className="dashboard-page-content keyword-config-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">AUTOMATIONS · CONFIGURATION</span><h1>Configure Automation</h1></div></div>
    <div className="automation-feedback error" role="alert">{error || 'Automation not found.'}</div>
    <Link className="automation-back-button" to="/dashboard/automations"><ArrowLeft size={14} /> Back to My Automations</Link>
  </div>

  return <div className="dashboard-page-content keyword-config-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">AUTOMATIONS · CONFIGURATION</span><h1>{automation.triggerType === 'direct_message' ? 'Configure Direct Message Triggers' : 'Configure Comment Triggers'}</h1><p>Set keyword rules and the permitted responses for {automation.name}.</p></div><span className="dashboard-date-chip"><i /> {automation.status.toUpperCase()}</span></div>
    <div className="automation-demo-notice"><ShieldCheck size={16} /><span><strong>{automation.triggerType === 'direct_message' ? 'Direct-message replies respect the 24-hour messaging window.' : 'Only one private reply is sent for each eligible comment.'}</strong><small>Meta app permissions, account eligibility, and platform policy apply. Attachments and sequential messages are not enabled.</small></span></div>

    <section className="dashboard-panel trigger-automation-summary">
      <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">AUTOMATION DETAILS</span><h2>{automation.name}</h2><p>{automation.platform} · {automation.accountName} · {automation.contentType}</p></div><Link className="automation-summary-edit-link" to={`/dashboard/automations/${encodeURIComponent(automation.id)}`}>View details</Link></div>
      <div className="trigger-summary-url"><span>POST / REEL URL</span><span className="trigger-summary-url-value" title={automation.postUrl}>{automation.postUrl}</span></div>
    </section>

    <div className="keyword-config-grid">
      <div className="keyword-config-main">
        <section className="dashboard-panel keyword-config-card">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">COMMENT TRIGGER</span><h2><BellRing size={17} /> Keyword rules</h2><p>At least one matching keyword is required before this automation can be activated.</p></div></div>
          <KeywordTagEditor keywords={keywords} onChange={setKeywords} disabled={false} />
          <button className="ai-inline-suggest" type="button" disabled={Boolean(aiTarget)} onClick={() => void generateAutomationSuggestion('keywords')}><Sparkles size={13} />{aiTarget === 'keywords' ? 'Generating…' : 'Suggest keywords with AI'}</button>
        </section>

        <section className="dashboard-panel keyword-config-card">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">MATCHING BEHAVIOR</span><h2>Keyword matching method</h2><p>Matching is case-insensitive.</p></div></div>
          <KeywordMatchMethodPicker value={method} onChange={setMethod} disabled={false} />
        </section>

        <section className="dashboard-panel keyword-config-card">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">PRIVATE RESPONSE</span><h2><Send size={17} /> Automatic private reply</h2><p>Only one text reply is sent for an eligible comment. Meta may reject ineligible recipients or events.</p></div></div>
          <label className="automation-form-field"><span>Private reply message</span><textarea rows={4} maxLength={1000} value={privateReply} onChange={(event) => setPrivateReply(event.target.value)} placeholder="Write the message DM Karo should send when a keyword matches." /></label>
          <button className="ai-inline-suggest" type="button" disabled={Boolean(aiTarget)} onClick={() => void generateAutomationSuggestion('private')}><Sparkles size={13} />{aiTarget === 'private' ? 'Generating…' : 'Draft with AI'}</button>
          <small className="automation-input-hint">{privateReply.length}/1000 characters. Plain text only; no attachment or sequence delivery.</small>
        </section>

        <section className="dashboard-panel keyword-config-card public-reply-card">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">OPTIONAL · PUBLIC COMMENT</span><h2><MessageCircleReply size={17} /> Public comment reply</h2><p>Post a text reply to the matching comment only when enabled.</p></div></div>
          <label className="keyword-rules-toggle public-reply-toggle"><span className="keyword-toggle-control"><input type="checkbox" checked={publicReplyEnabled} onChange={(event) => setPublicReplyEnabled(event.target.checked)} /><i /></span><span><strong>Enable public reply</strong><small>Only for the comment that triggered this automation.</small></span><em className={publicReplyEnabled ? 'enabled' : 'disabled'}>{publicReplyEnabled ? 'ENABLED' : 'DISABLED'}</em></label>
          {publicReplyEnabled && <label className="automation-form-field"><span>Public reply text</span><textarea rows={3} maxLength={1000} value={publicReply} onChange={(event) => setPublicReply(event.target.value)} placeholder="Thanks for your comment!" /></label>}
          {publicReplyEnabled && <button className="ai-inline-suggest" type="button" disabled={Boolean(aiTarget)} onClick={() => void generateAutomationSuggestion('public')}><Sparkles size={13} />{aiTarget === 'public' ? 'Generating…' : 'Draft with AI'}</button>}
        </section>
      </div>
    </div>

    {error && <div className="automation-feedback error" role="alert"><AlertCircle size={15} />{error}</div>}
    {notice && <div className="automation-feedback success" role="status"><Check size={15} />{notice}</div>}
    <div className="automation-wizard-actions">
      <Link className="automation-back-button" to="/dashboard/automations"><ArrowLeft size={14} /> Back to automations</Link>
      <button className="btn btn-primary" type="button" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save Configuration'}</button>
    </div>
  </div>
}
