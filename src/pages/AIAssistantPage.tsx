import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { AlertCircle, Bot, ChevronDown, Eraser, KeyRound, Plus, Send, Sparkles } from 'lucide-react'
import {
  askAIAssist,
  clearAIConversation,
  getAIConversation,
  getAIKnowledge,
  getAISettings,
  getAIUsage,
  listAIConversations,
  saveAIKnowledge,
  sendAIMessage,
  updateAISettings,
  type AIAction,
  type AIConversation,
  type AIKnowledge,
  type AIMessage,
  type AIProvider,
  type AISettings,
  type AIUsage,
} from '../services/aiApi'
import '../ai-assistant.css'

const blankKnowledge: AIKnowledge = {
  business_name: '',
  description: '',
  products_services: '',
  faqs: '',
  website_information: '',
  custom_instructions: '',
  updated_at: null,
}

const actions: Array<{ value: AIAction; label: string }> = [
  { value: 'draft_message', label: 'Draft a DM' },
  { value: 'suggest_keywords', label: 'Suggest trigger keywords' },
  { value: 'public_reply', label: 'Draft a public reply' },
  { value: 'improve_message', label: 'Improve wording' },
  { value: 'translate', label: 'Translate a message' },
  { value: 'summarize', label: 'Summarize a conversation' },
  { value: 'suggested_reply', label: 'Suggest an inbox reply' },
  { value: 'classify', label: 'Estimate intent and sentiment' },
]

export function AIAssistantPage() {
  const [settings, setSettings] = useState<AISettings | null>(null)
  const [usage, setUsage] = useState<AIUsage | null>(null)
  const [knowledge, setKnowledge] = useState<AIKnowledge>(blankKnowledge)
  const [conversations, setConversations] = useState<AIConversation[]>([])
  const [conversationId, setConversationId] = useState('')
  const [messages, setMessages] = useState<AIMessage[]>([])
  const [chatText, setChatText] = useState('')
  const [action, setAction] = useState<AIAction>('draft_message')
  const [actionInput, setActionInput] = useState('')
  const [actionContext, setActionContext] = useState('')
  const [language, setLanguage] = useState('')
  const [suggestion, setSuggestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const selectedProvider = useMemo(
    () => settings?.providers.find((provider) => provider.provider === settings.selected_provider),
    [settings],
  )

  useEffect(() => {
    let active = true
    Promise.all([getAISettings(), getAIUsage(), getAIKnowledge(), listAIConversations()])
      .then(([nextSettings, nextUsage, nextKnowledge, nextConversations]) => {
        if (!active) return
        setSettings(nextSettings)
        setUsage(nextUsage)
        setKnowledge(nextKnowledge)
        setConversations(nextConversations)
        if (nextConversations[0]) {
          setConversationId(nextConversations[0].id)
          return getAIConversation(nextConversations[0].id).then((conversation) => {
            if (active) setMessages(conversation.messages)
          })
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'Could not load AI settings.')
      })
      .finally(() => { if (active) setInitialLoading(false) })
    return () => { active = false }
  }, [])

  const refreshUsage = async () => {
    const [nextUsage, nextConversations] = await Promise.all([getAIUsage(), listAIConversations()])
    setUsage(nextUsage)
    setConversations(nextConversations)
  }

  const selectConversation = async (id: string) => {
    setError('')
    setNotice('')
    setConversationId(id)
    try {
      const conversation = await getAIConversation(id)
      setMessages(conversation.messages)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load this conversation.')
    }
  }

  const startNewChat = () => {
    setConversationId('')
    setMessages([])
    setError('')
    setNotice('')
  }

  const submitChat = async (event: FormEvent) => {
    event.preventDefault()
    const text = chatText.trim()
    if (!text || busy) return
    const userMessage: AIMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      provider: null,
      model: null,
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, userMessage])
    setChatText('')
    setBusy(true)
    setError('')
    try {
      const response = await sendAIMessage(text, conversationId || undefined)
      setConversationId(response.conversation_id)
      setMessages((current) => [...current, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.answer,
        provider: response.provider,
        model: response.model,
        created_at: new Date().toISOString(),
      }])
      await refreshUsage()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The AI response could not be generated.')
    } finally {
      setBusy(false)
    }
  }

  const clearChat = async () => {
    if (!conversationId) {
      startNewChat()
      return
    }
    setBusy(true)
    setError('')
    try {
      await clearAIConversation(conversationId)
      setConversations((current) => current.filter((item) => item.id !== conversationId))
      startNewChat()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not clear this conversation.')
    } finally {
      setBusy(false)
    }
  }

  const chooseProvider = async (provider: AIProvider) => {
    const choice = settings?.providers.find((item) => item.provider === provider)
    if (!choice?.configured) return
    setBusy(true)
    setError('')
    try {
      setSettings(await updateAISettings(provider, choice.model))
      setNotice(`AI provider set to ${provider === 'openai' ? 'OpenAI' : 'Google Gemini'}.`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update the AI provider.')
    } finally {
      setBusy(false)
    }
  }

  const saveKnowledge = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setKnowledge(await saveAIKnowledge(knowledge))
      setNotice('Organization business knowledge saved.')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save business knowledge.')
    } finally {
      setBusy(false)
    }
  }

  const generateSuggestion = async (event: FormEvent) => {
    event.preventDefault()
    if (!actionInput.trim()) {
      setError('Enter content for the selected AI tool.')
      return
    }
    setBusy(true)
    setError('')
    setSuggestion('')
    setNotice('')
    try {
      const result = await askAIAssist(action, actionInput, actionContext, language)
      setSuggestion(result.result)
      setNotice(`Suggestion generated with ${result.provider === 'openai' ? 'OpenAI' : 'Gemini'} · ${result.model}. Review it before use.`)
      setUsage(await getAIUsage())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The AI suggestion could not be generated.')
    } finally {
      setBusy(false)
    }
  }

  if (initialLoading) return <div className="dashboard-page-content" role="status">Loading AI workspace…</div>

  return <div className="dashboard-page-content ai-workspace">
    <div className="dashboard-welcome-row">
      <div><span className="dashboard-page-eyebrow">DM KARO · AI WORKSPACE</span><h1>AI Assistant <span className="ai-beta-pill">AI SUGGESTIONS</span></h1><p>Get writing help and workflow ideas. Generated content is not verified and is never sent automatically.</p></div>
      <span className="dashboard-date-chip"><i /> {selectedProvider ? selectedProvider.provider.toUpperCase() : 'NOT CONFIGURED'}</span>
    </div>

    {error && <div className="automation-feedback error" role="alert"><AlertCircle size={15} />{error}</div>}
    {notice && <div className="automation-feedback success" role="status">{notice}</div>}
    {!settings?.providers.some((provider) => provider.configured) && <div className="ai-provider-warning" role="status"><KeyRound size={17} /><span><strong>AI provider is not configured</strong><small>Ask your service operator to set OPENAI_API_KEY or GEMINI_API_KEY on the backend. Keys are never entered in or sent from this page.</small></span></div>}

    <section className="ai-controls-row">
      <div className="dashboard-panel ai-provider-card">
        <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">PROVIDER</span><h2><Bot size={17} /> AI model</h2><p>Provider secrets are held only by the backend.</p></div></div>
        <div className="ai-provider-options">
          {settings?.providers.map((provider) => <button
            type="button"
            key={provider.provider}
            className={`ai-provider-option${settings.selected_provider === provider.provider ? ' selected' : ''}`}
            onClick={() => void chooseProvider(provider.provider)}
            disabled={busy || !provider.configured}
            title={!provider.configured ? 'Not configured by the service operator' : provider.model}
          ><strong>{provider.provider === 'openai' ? 'OpenAI' : 'Google Gemini'}</strong><small>{provider.configured ? provider.model : 'Not configured'}</small></button>)}
        </div>
      </div>
      <div className="dashboard-panel ai-usage-card">
        <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">USAGE · LAST 30 DAYS</span><h2><Sparkles size={16} /> Request usage</h2></div></div>
        <div className="ai-usage-metrics"><strong>{usage?.request_count ?? 0}<small> requests</small></strong><span>Daily limit: {usage?.daily_request_limit ?? 0}</span></div>
        <div className="ai-usage-details"><span>{(usage?.input_tokens ?? 0).toLocaleString()} input tokens</span><span>{(usage?.output_tokens ?? 0).toLocaleString()} output tokens</span><span>{usage?.estimated_cost_usd == null ? 'Cost estimate not configured' : `$${usage.estimated_cost_usd.toFixed(6)} estimated`}</span></div>
      </div>
    </section>

    <section className="ai-main-grid">
      <div className="dashboard-panel ai-chat-panel">
        <div className="dashboard-panel-heading ai-chat-heading">
          <div><span className="dashboard-section-kicker">CONVERSATION</span><h2>Ask DM Karo AI</h2><p>Answers can be inaccurate; verify important information.</p></div>
          <div className="ai-chat-actions"><button type="button" className="ai-icon-action" onClick={startNewChat} aria-label="Start new chat" title="Start new chat"><Plus size={16} /></button><button type="button" className="ai-icon-action" onClick={() => void clearChat()} disabled={busy} aria-label="Clear chat" title="Clear chat"><Eraser size={15} /></button></div>
        </div>
        {conversations.length > 0 && <label className="ai-conversation-picker"><span>Recent conversation</span><select value={conversationId} onChange={(event) => void selectConversation(event.target.value)}><option value="">New conversation</option>{conversations.map((item) => <option value={item.id} key={item.id}>{item.title}</option>)}</select><ChevronDown size={14} /></label>}
        <div className="ai-chat-messages" aria-live="polite">
          {messages.length === 0 && <div className="ai-empty-chat"><span><Bot size={22} /></span><strong>How can I help?</strong><small>Ask about DM Karo or get help planning a customer-friendly response.</small></div>}
          {messages.map((message) => <article key={message.id} className={`ai-message ${message.role}`}><span className="ai-message-role">{message.role === 'assistant' ? 'DM KARO AI' : 'YOU'}</span><p>{message.content}</p>{message.role === 'assistant' && message.provider && <small>{message.provider} · {message.model} · AI-generated</small>}</article>)}
          {busy && <div className="ai-thinking" role="status"><span className="ai-pulse" /> Generating a response…</div>}
        </div>
        <form className="ai-chat-form" onSubmit={(event) => void submitChat(event)}>
          <label className="sr-only" htmlFor="ai-chat-input">Message the AI assistant</label>
          <textarea id="ai-chat-input" rows={2} maxLength={12000} value={chatText} onChange={(event) => setChatText(event.target.value)} placeholder="Ask a question about DM Karo…" disabled={busy} />
          <button type="submit" className="btn btn-primary" disabled={busy || !chatText.trim() || !selectedProvider}><Send size={14} />{busy ? 'Working…' : 'Send'}</button>
        </form>
        <small className="ai-privacy-note">Avoid sharing passwords, tokens, payment details, or other sensitive information. Conversation content is sent to the configured AI provider.</small>
      </div>

      <div className="ai-tools-column">
        <section className="dashboard-panel ai-tools-panel">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">WRITING & INBOX TOOLS</span><h2><Sparkles size={17} /> AI suggestions</h2><p>Review and edit every result before using it.</p></div></div>
          <form className="ai-tool-form" onSubmit={(event) => void generateSuggestion(event)}>
            <label className="automation-form-field"><span>What do you need?</span><select value={action} onChange={(event) => { setAction(event.target.value as AIAction); setSuggestion('') }}>{actions.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
            <label className="automation-form-field"><span>Message or conversation</span><textarea rows={4} maxLength={12000} value={actionInput} onChange={(event) => setActionInput(event.target.value)} placeholder="Enter text to draft, improve, summarize, or classify." /></label>
            <label className="automation-form-field"><span>Optional context</span><textarea rows={2} maxLength={12000} value={actionContext} onChange={(event) => setActionContext(event.target.value)} placeholder="Add relevant details or goals." /></label>
            {action === 'translate' && <label className="automation-form-field"><span>Target language</span><input value={language} onChange={(event) => setLanguage(event.target.value)} maxLength={80} placeholder="e.g. Hindi" /></label>}
            <button type="submit" className="btn btn-primary ai-generate-button" disabled={busy || !selectedProvider}><Sparkles size={14} />{busy ? 'Generating…' : 'Generate suggestion'}</button>
          </form>
          {suggestion && <div className="ai-suggestion-result"><span>AI-GENERATED · REVIEW BEFORE USE</span><p>{suggestion}</p></div>}
          {action === 'classify' && <small className="ai-privacy-note">Intent, lead intent, sentiment, and FAQ results are estimates—not verified customer facts.</small>}
        </section>

        <section className="dashboard-panel ai-knowledge-panel">
          <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">ORGANIZATION-ONLY CONTEXT</span><h2>Business knowledge</h2><p>Entered information may be included in this organization’s AI requests. No website is fetched or scraped.</p></div></div>
          <form className="ai-tool-form" onSubmit={(event) => void saveKnowledge(event)}>
            <label className="automation-form-field"><span>Business name</span><input value={knowledge.business_name} onChange={(event) => setKnowledge({ ...knowledge, business_name: event.target.value })} maxLength={160} /></label>
            <label className="automation-form-field"><span>Description</span><textarea rows={2} value={knowledge.description} onChange={(event) => setKnowledge({ ...knowledge, description: event.target.value })} maxLength={4000} /></label>
            <label className="automation-form-field"><span>Products and services</span><textarea rows={3} value={knowledge.products_services} onChange={(event) => setKnowledge({ ...knowledge, products_services: event.target.value })} maxLength={8000} /></label>
            <label className="automation-form-field"><span>FAQs</span><textarea rows={3} value={knowledge.faqs} onChange={(event) => setKnowledge({ ...knowledge, faqs: event.target.value })} maxLength={8000} /></label>
            <label className="automation-form-field"><span>Website information you provide</span><textarea rows={2} value={knowledge.website_information} onChange={(event) => setKnowledge({ ...knowledge, website_information: event.target.value })} maxLength={8000} /></label>
            <label className="automation-form-field"><span>Custom instructions</span><textarea rows={2} value={knowledge.custom_instructions} onChange={(event) => setKnowledge({ ...knowledge, custom_instructions: event.target.value })} maxLength={4000} /></label>
            <button type="submit" className="btn btn-secondary" disabled={busy}>Save business knowledge</button>
          </form>
        </section>
      </div>
    </section>
  </div>
}
