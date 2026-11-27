import { useState, type FormEvent } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { AuthFeedback } from '../components/AuthFeedback'
import { AuthFormField } from '../components/AuthFormField'
import { AuthLayout } from '../components/AuthLayout'
import { GoogleButton } from '../components/GoogleButton'
import { AuthApiError } from '../services/authApi'

type RegistrationValues = {
  name: string
  businessName: string
  email: string
  mobile: string
  password: string
  confirmPassword: string
}
type RegistrationErrors = Partial<Record<keyof RegistrationValues | 'terms', string>>

const emptyValues: RegistrationValues = { name: '', businessName: '', email: '', mobile: '', password: '', confirmPassword: '' }

export function RegisterPage() {
  const { register } = useAuth()
  const [values, setValues] = useState(emptyValues)
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [errors, setErrors] = useState<RegistrationErrors>({})
  const [feedback, setFeedback] = useState({ message: '', kind: 'error' as 'error' | 'success' })
  const [loading, setLoading] = useState(false)
  const [registered, setRegistered] = useState(false)

  const updateValue = (field: keyof RegistrationValues, value: string) => {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: '' }))
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const digits = values.mobile.replace(/\D/g, '')
    const nextErrors: RegistrationErrors = {
      name: values.name.trim() ? '' : 'Enter your full name.',
      businessName: values.businessName.trim() ? '' : 'Enter your business name.',
      email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim()) ? '' : 'Enter a valid email address.',
      mobile: /^\+?[0-9\s()-]+$/.test(values.mobile.trim()) && digits.length >= 7 && digits.length <= 15 ? '' : 'Enter a valid mobile number (7–15 digits).',
      password: values.password.length >= 8 && values.password.length <= 128 ? '' : 'Use 8–128 characters.',
      confirmPassword: values.confirmPassword && values.confirmPassword === values.password ? '' : 'Passwords do not match.',
      terms: acceptedTerms ? '' : 'Accept the Terms and Privacy Policy to continue.',
    }
    setErrors(nextErrors)
    if (Object.values(nextErrors).some(Boolean)) return

    setFeedback({ message: '', kind: 'error' })
    setLoading(true)
    try {
      const result = await register({
        name: values.name.trim(),
        business_name: values.businessName.trim(),
        email: values.email.trim().toLowerCase(),
        mobile_number: values.mobile.trim(),
        password: values.password,
        confirm_password: values.confirmPassword,
      })
      setRegistered(true)
      setFeedback({ message: result.message, kind: 'success' })
    } catch (error) {
      if (error instanceof AuthApiError && error.fields.length) {
        const fieldMap: Record<string, keyof RegistrationValues> = {
          name: 'name',
          business_name: 'businessName',
          email: 'email',
          mobile_number: 'mobile',
          password: 'password',
          confirm_password: 'confirmPassword',
        }
        setErrors(Object.fromEntries(error.fields.flatMap((field) => {
          const key = fieldMap[field.field.split('.').at(-1) || '']
          return key ? [[key, field.message]] : []
        })))
      }
      setFeedback({ message: error instanceof Error ? error.message : 'Your account could not be created.', kind: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return <AuthLayout heading="Create your account" description="Create your secure DM Karo workspace.">
    <form className="auth-form registration-form" onSubmit={handleSubmit} noValidate>
      <div className="auth-form-grid">
        <AuthFormField id="register-name" label="Full name" autoComplete="name" placeholder="Alex Morgan" value={values.name} onChange={(value) => updateValue('name', value)} error={errors.name} />
        <AuthFormField id="register-business" label="Business name" autoComplete="organization" placeholder="Your business" value={values.businessName} onChange={(value) => updateValue('businessName', value)} error={errors.businessName} />
      </div>
      <AuthFormField id="register-email" label="Email address" type="email" autoComplete="email" placeholder="you@company.com" value={values.email} onChange={(value) => updateValue('email', value)} error={errors.email} />
      <AuthFormField id="register-mobile" label="Mobile number" type="tel" autoComplete="tel" placeholder="+91 98765 43210" value={values.mobile} onChange={(value) => updateValue('mobile', value)} error={errors.mobile} />
      <div className="auth-form-grid">
        <AuthFormField id="register-password" label="Password" type="password" autoComplete="new-password" placeholder="At least 8 characters" value={values.password} onChange={(value) => updateValue('password', value)} error={errors.password} minLength={8} />
        <AuthFormField id="register-confirm-password" label="Confirm password" type="password" autoComplete="new-password" placeholder="Repeat your password" value={values.confirmPassword} onChange={(value) => updateValue('confirmPassword', value)} error={errors.confirmPassword} />
      </div>
      <div className="auth-terms-wrap"><label className="auth-checkbox"><input type="checkbox" checked={acceptedTerms} onChange={(event) => { setAcceptedTerms(event.target.checked); setErrors((current) => ({ ...current, terms: '' })) }} /><span>I agree to the <Link to="/terms">Terms</Link> and <Link to="/privacy">Privacy Policy</Link>.</span></label>{errors.terms && <span className="auth-field-error">{errors.terms}</span>}</div>
      <AuthFeedback message={feedback.message} kind={feedback.kind} />
      {registered && <p className="auth-switch">Already verified? <Link to="/login">Sign in</Link></p>}
      {!registered && <button className="btn btn-primary auth-submit" type="submit" disabled={loading}>{loading ? <><span className="auth-spinner" /> Creating account…</> : <>Create Account <ArrowRight size={16} /></>}</button>}
      <p className="auth-demo-help">Your password is securely hashed. Email verification is required before sign in.</p>
    </form>
    <div className="auth-divider"><span>or</span></div>
    <GoogleButton />
    <p className="auth-switch">Already have an account? <Link to="/login">Login</Link></p>
  </AuthLayout>
}
