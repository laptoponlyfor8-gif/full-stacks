import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, ArrowLeft, ArrowRight, Check, Eye, Link2, RotateCcw, Sparkles } from 'lucide-react'
import { AutomationSummaryCard } from '../components/dashboard/AutomationSummaryCard'
import { AutomationWizardSteps } from '../components/dashboard/AutomationWizardSteps'
import { SocialAccountSelector } from '../components/dashboard/SocialAccountSelector'
import { createAutomation, getAutomation, updateAutomation } from '../services/automationsApi'
import { useSocialAccounts } from '../hooks/useSocialAccounts'
import { validateAutomationFields, validatePostUrl, type AutomationFieldErrors, type AutomationFields } from '../utils/automationValidation'
import type { AutomationContentType, AutomationPlatform, SocialPlatform } from '../types'

const initialFields: AutomationFields = { name: '', platform: '', accountId: '', contentType: '', postUrl: '' }

const contentTypes: Record<AutomationPlatform, AutomationContentType[]> = {
  Instagram: ['Instagram Reel', 'Instagram Post'],
  Facebook: ['Facebook Post'],
}

export function CreateAutomationPage() {
  const navigate = useNavigate()
  const { accounts: socialAccounts } = useSocialAccounts()
  const [searchParams] = useSearchParams()
  const editId = searchParams.get('edit')
  const [fields, setFields] = useState<AutomationFields>(initialFields)
  const [loadingEdit, setLoadingEdit] = useState(Boolean(editId))
  const [missingEdit, setMissingEdit] = useState(false)
  const [triggerType, setTriggerType] = useState<'comment' | 'direct_message'>('comment')
  const [step, setStep] = useState(1)
  const [errors, setErrors] = useState<AutomationFieldErrors>({})
  const [feedback, setFeedback] = useState('')
  const [feedbackError, setFeedbackError] = useState(false)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [saving, setSaving] = useState(false)
  const selectedAccount = socialAccounts.find((account) => account.id === fields.accountId && account.is_connected && account.connection_status === 'connected')

  useEffect(() => {
    if (!editId) return
    let active = true
    getAutomation(editId)
      .then((saved) => {
        if (!active) return
        setFields({
          name: saved.name,
          platform: saved.platform,
          accountId: saved.accountId,
          contentType: saved.contentType,
          postUrl: saved.postUrl,
        })
        setTriggerType(saved.triggerType ?? 'comment')
      })
      .catch((reason: unknown) => {
        if (active) {
          setMissingEdit(true)
          setFeedback(reason instanceof Error ? reason.message : 'Could not load this automation.')
        }
      })
      .finally(() => { if (active) setLoadingEdit(false) })
    return () => { active = false }
  }, [editId])

  const updateField = <K extends keyof AutomationFields>(key: K, value: AutomationFields[K]) => {
    setFields((current) => ({ ...current, [key]: value }))
    setErrors((current) => ({ ...current, [key]: '' }))
    setFeedback('')
    setFeedbackError(false)
    if (key === 'platform' || key === 'postUrl') setPreviewVisible(false)
  }

  const validateStep = (currentStep: number): boolean => {
    const nextErrors: AutomationFieldErrors = {}
    if (currentStep === 1) {
      if (!fields.name.trim()) nextErrors.name = 'Enter an automation name.'
      if (!fields.platform) nextErrors.platform = 'Select Instagram or Facebook.'
      if (!fields.contentType) nextErrors.contentType = 'Select a content type.'
    } else if (currentStep === 2) {
      if (!fields.accountId || !selectedAccount) nextErrors.accountId = 'Select a connected social account.'
    } else if (currentStep === 3) {
      const urlError = triggerType === 'comment' ? validatePostUrl(fields.postUrl, fields.platform) : ''
      if (urlError) nextErrors.postUrl = urlError
    }
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length) {
      setFeedback('Please fix the highlighted fields to continue.')
      return false
    }
    setFeedback('')
    return true
  }

  const saveDraft = async (continueToConfigure: boolean) => {
    const nextErrors = validateAutomationFields(fields)
    if (triggerType === 'direct_message') delete nextErrors.postUrl
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors)
      const firstInvalidStep = nextErrors.name || nextErrors.platform || nextErrors.contentType ? 1 : nextErrors.accountId ? 2 : 3
      setStep(firstInvalidStep)
      setFeedback('Complete all required fields before saving your draft.')
      return
    }
    if (!selectedAccount || !fields.platform || !fields.contentType) {
      setFeedback('The selected social account is no longer connected. Select an active Meta account.')
      setErrors((current) => ({ ...current, accountId: 'Select a connected social account.' }))
      setStep(2)
      return
    }

    setSaving(true)
    setFeedback('')
    try {
      const input = {
        name: fields.name.trim(),
        social_account_id: selectedAccount.id,
        platform: fields.platform.toLowerCase() as 'instagram' | 'facebook',
        trigger_type: triggerType,
        content_type: fields.contentType,
        content_url: fields.postUrl.trim(),
      }
      const saved = editId ? await updateAutomation(editId, input) : await createAutomation(input)
      setFeedbackError(false)
      setFeedback('Automation draft saved to your account.')
      if (continueToConfigure) navigate(`/dashboard/automations/configure?id=${encodeURIComponent(saved.id)}`, { state: { notice: 'Draft saved. Configure real keyword and reply settings before activation.' } })
      else navigate('/dashboard/automations', { state: { notice: 'Automation draft saved.' } })
    } catch (error) {
      setFeedbackError(true)
      setFeedback(error instanceof Error ? error.message : 'The automation could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  const handlePreview = () => {
    if (triggerType === 'direct_message') return
    const urlError = validatePostUrl(fields.postUrl, fields.platform)
    setErrors((current) => ({ ...current, postUrl: urlError }))
    setPreviewVisible(!urlError)
  }

  const advanceStep = () => {
    if (!validateStep(step)) return
    setStep(step === 2 && triggerType === 'direct_message' ? 4 : step + 1)
  }

  const platformValue = fields.platform ? fields.platform.toLowerCase() as SocialPlatform : undefined
  const isEditing = Boolean(editId)
  if (loadingEdit) return <div className="dashboard-page-content" role="status">Loading automation…</div>

  return <div className="dashboard-page-content automation-builder-page">
    <div className="dashboard-welcome-row"><div><span className="dashboard-page-eyebrow">AUTOMATIONS · BUILDER</span><h1>{isEditing ? 'Edit Automation' : 'Create New Automation'}</h1><p>Configure a real workflow for a connected Instagram or Facebook account.</p></div><span className="dashboard-date-chip"><i /> BACKEND CONNECTED</span></div>
    {missingEdit && <div className="automation-feedback error" role="alert"><AlertCircle size={16} /> {feedback || 'This automation could not be found.'}</div>}
    <div className="automation-demo-notice"><span><strong>Post ownership is checked with Meta before saving.</strong><small>Only an eligible connected account with the necessary Meta permissions can activate the workflow.</small></span></div>
    <AutomationWizardSteps currentStep={step} />
    <div className="automation-builder-grid">
      <section className="dashboard-panel automation-step-panel">
        <div className="automation-step-heading"><span className="automation-step-large">{String(step).padStart(2, '0')}</span><div><span className="dashboard-section-kicker">STEP {step} OF 4</span><h2>{step === 1 ? 'Automation details' : step === 2 ? 'Select social account' : step === 3 ? 'Add Reel or Post URL' : 'Review your automation'}</h2><p>{step === 1 ? 'Give your automation a name and choose where it will run.' : step === 2 ? 'Choose a connected Meta account for this workflow.' : step === 3 ? 'Add the permalink for a post or Reel on the selected account.' : 'Review your settings before saving this draft.'}</p></div></div>
        {step === 1 && <div className="automation-form-fields">
          <div className="automation-form-field"><label htmlFor="automation-name">Automation Name <span>*</span></label><input id="automation-name" value={fields.name} onChange={(event) => updateField('name', event.target.value)} placeholder="e.g. Summer Reel welcome DM" aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'automation-name-error' : undefined} />{errors.name && <small className="automation-field-error" id="automation-name-error">{errors.name}</small>}</div>
          <div className="automation-form-field"><label htmlFor="automation-trigger">Trigger type <span>*</span></label><select id="automation-trigger" value={triggerType} disabled={isEditing} onChange={(event) => { setTriggerType(event.target.value as 'comment' | 'direct_message'); setFeedback('') }}><option value="comment">Matching comment</option><option value="direct_message">Incoming direct message</option></select><small className="automation-input-hint">{isEditing ? 'Create a separate automation to use a different trigger type.' : 'Direct-message replies are only sent inside Meta’s permitted messaging window.'}</small></div>
          <div className="automation-form-field"><label htmlFor="automation-platform">Select Social Platform <span>*</span></label><select id="automation-platform" value={fields.platform} onChange={(event) => { const platform = event.target.value as AutomationPlatform | ''; updateField('platform', platform); updateField('accountId', ''); updateField('contentType', '') }} aria-invalid={Boolean(errors.platform)}><option value="">Choose a platform</option><option value="Instagram">Instagram</option><option value="Facebook">Facebook</option></select>{errors.platform && <small className="automation-field-error">{errors.platform}</small>}</div>
          <div className="automation-form-field"><label htmlFor="automation-content-type">Select Content Type <span>*</span></label><select id="automation-content-type" value={fields.contentType} onChange={(event) => updateField('contentType', event.target.value as AutomationContentType | '')} disabled={!fields.platform} aria-invalid={Boolean(errors.contentType)}><option value="">Choose a content type</option>{fields.platform && contentTypes[fields.platform].map((contentType) => <option value={contentType} key={contentType}>{contentType}</option>)}</select>{errors.contentType && <small className="automation-field-error">{errors.contentType}</small>}</div>
        </div>}
        {step === 2 && <div className="automation-form-fields"><SocialAccountSelector value={fields.accountId} onChange={(value) => updateField('accountId', value)} label="Connected social account" platform={platformValue} />{errors.accountId && <small className="automation-field-error">{errors.accountId}</small>}<div className="automation-account-help"><span>No social accounts connected yet?</span><button type="button" onClick={() => navigate('/dashboard/accounts')}>Connect Account <ArrowRight size={13} /></button></div><p className="automation-safe-note">Only active accounts confirmed by the Meta connection API appear here.</p></div>}
        {step === 3 && triggerType === 'comment' && <div className="automation-form-fields"><div className="automation-form-field"><label htmlFor="automation-post-url">Instagram Reel or Facebook Post URL <span>*</span></label><div className={`automation-url-field${errors.postUrl ? ' has-error' : ''}`}><Link2 size={17} /><input id="automation-post-url" inputMode="url" value={fields.postUrl} onChange={(event) => updateField('postUrl', event.target.value)} placeholder="Paste your Instagram Reel or Facebook Post URL here" aria-invalid={Boolean(errors.postUrl)} aria-describedby={errors.postUrl ? 'automation-url-error' : undefined} /><button type="button" onClick={() => { updateField('postUrl', ''); setPreviewVisible(false) }} disabled={!fields.postUrl}>Clear URL</button></div>{errors.postUrl && <small className="automation-field-error" id="automation-url-error">{errors.postUrl}</small>}<small className="automation-input-hint">Use a permalink belonging to the selected connected account.</small></div><button className="automation-preview-button" type="button" onClick={handlePreview}><Eye size={15} /> Check URL</button>{previewVisible && <div className="automation-url-preview"><span className="automation-preview-tag">URL FORMAT CHECK</span><dl><div><dt>Platform</dt><dd>{fields.platform}</dd></div><div><dt>Content type</dt><dd>{fields.contentType}</dd></div><div><dt>Submitted URL</dt><dd>{fields.postUrl}</dd></div><div><dt>Preview status</dt><dd>Format accepted · Meta validation runs when saving</dd></div></dl><p>The backend verifies content ownership through Meta when the draft is saved.</p></div>}</div>}
        {step === 4 && <div className="automation-form-fields"><AutomationSummaryCard fields={fields} accountName={selectedAccount?.account_name ?? ''} /><div className="automation-safe-note"><Check size={15} /> Saving creates a backend draft. It will not run until it is configured and activated.</div></div>}
        {feedback && <div className={`automation-feedback ${feedbackError || errors.name || errors.platform || errors.accountId || errors.contentType || errors.postUrl ? 'error' : 'success'}`} role={feedbackError || errors.name || errors.platform || errors.accountId || errors.contentType || errors.postUrl ? 'alert' : 'status'}>{feedbackError || errors.name || errors.platform || errors.accountId || errors.contentType || errors.postUrl ? <AlertCircle size={15} /> : <Check size={15} />}{feedback}</div>}
        <div className="automation-wizard-actions">
          <button className="automation-cancel-button" type="button" onClick={() => navigate('/dashboard/automations')}>Cancel</button>
          <div>{step > 1 && <button className="automation-back-button" type="button" onClick={() => { setStep(step === 4 && triggerType === 'direct_message' ? 2 : step - 1); setFeedback('') }}><ArrowLeft size={14} /> Back</button>}{step < 4 ? <button className="btn btn-primary" type="button" onClick={advanceStep}>Continue <ArrowRight size={14} /></button> : <><button className="automation-save-draft" type="button" disabled={saving} onClick={() => void saveDraft(false)}>{saving ? 'Saving…' : 'Save as Draft'}</button><button className="btn btn-primary" type="button" disabled={saving} onClick={() => void saveDraft(true)}>Configure Triggers <ArrowRight size={14} /></button></>}</div>
        </div>
      </section>
      <aside className="automation-builder-aside"><div className="dashboard-panel automation-aside-card"><span className="automation-aside-icon"><RotateCcw size={17} /></span><span className="dashboard-section-kicker">HOW IT WORKS</span><h3>Simple setup, clear control.</h3><p>Choose an account, link a supported post, then review everything before saving your draft.</p><ol><li><i>1</i> Choose Instagram or Facebook</li><li><i>2</i> Select a connected Meta account</li><li><i>3</i> Verify the permalink and save the draft</li></ol></div><div className="automation-preview-disclaimer"><Sparkles size={15} /><span><strong>Policy and access limits apply</strong><small>Meta may reject events or messages when permissions, account eligibility, or messaging windows do not allow them.</small></span></div></aside>
    </div>
  </div>
}
