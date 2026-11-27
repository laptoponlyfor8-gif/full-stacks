import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

type AuthFormFieldProps = {
  id: string
  label: string
  type?: 'text' | 'email' | 'tel' | 'password'
  autoComplete?: string
  placeholder?: string
  value: string
  onChange: (value: string) => void
  error?: string
  required?: boolean
  minLength?: number
  pattern?: string
}

export function AuthFormField({ id, label, type = 'text', autoComplete, placeholder, value, onChange, error, required = true, minLength, pattern }: AuthFormFieldProps) {
  const [passwordVisible, setPasswordVisible] = useState(false)
  const isPassword = type === 'password'
  const inputType = isPassword && passwordVisible ? 'text' : type

  return <div className="auth-field">
    <label htmlFor={id}>{label}</label>
    <div className={`auth-input-wrap${error ? ' has-error' : ''}`}>
      <input
        id={id}
        name={id}
        type={inputType}
        autoComplete={autoComplete}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        minLength={minLength}
        pattern={pattern}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {isPassword && <button className="auth-password-toggle" type="button" aria-label={passwordVisible ? 'Hide password' : 'Show password'} aria-pressed={passwordVisible} onClick={() => setPasswordVisible(!passwordVisible)}>{passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}</button>}
    </div>
    {error && <span className="auth-field-error" id={`${id}-error`}>{error}</span>}
  </div>
}
