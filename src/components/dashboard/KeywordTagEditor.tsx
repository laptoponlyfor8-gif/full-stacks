import { useState } from 'react'
import { Check, Pencil, Plus, X } from 'lucide-react'

export function KeywordTagEditor({ keywords, onChange, error, disabled }: {
  keywords: string[]
  onChange: (keywords: string[]) => void
  error?: string
  disabled: boolean
}) {
  const [value, setValue] = useState('')
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [inputError, setInputError] = useState('')

  const commit = () => {
    const keyword = value.trim().replace(/\s+/g, ' ')
    if (!keyword) {
      setInputError('Enter a keyword or phrase.')
      return
    }
    const duplicate = keywords.some((existing, index) => index !== editingIndex && existing.toLocaleLowerCase() === keyword.toLocaleLowerCase())
    if (duplicate) {
      setInputError('That keyword is already in the list.')
      return
    }
    if (editingIndex === null) onChange([...keywords, keyword])
    else onChange(keywords.map((existing, index) => index === editingIndex ? keyword : existing))
    setValue('')
    setEditingIndex(null)
    setInputError('')
  }

  const edit = (index: number) => {
    setEditingIndex(index)
    setValue(keywords[index])
  }

  const cancelEdit = () => {
    setEditingIndex(null)
    setValue('')
  }

  return <div className="keyword-editor">
    <div className="keyword-editor-input-row">
      <label className="sr-only" htmlFor="keyword-input">{editingIndex === null ? 'Add keyword or phrase' : 'Edit keyword or phrase'}</label>
      <input id="keyword-input" value={value} onChange={(event) => { setValue(event.target.value); setInputError('') }} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); commit() } }} placeholder={editingIndex === null ? 'Type a keyword or phrase, e.g. LINK' : 'Edit keyword or phrase'} disabled={disabled} aria-describedby={inputError || error ? 'keyword-error' : undefined} />
      {editingIndex !== null && <button className="keyword-editor-cancel" type="button" onClick={cancelEdit} aria-label="Cancel keyword edit"><X size={14} /></button>}
      <button className="btn btn-primary keyword-add-button" type="button" onClick={commit} disabled={disabled || !value.trim()}><>{editingIndex === null ? <Plus size={14} /> : <Check size={14} />}{editingIndex === null ? 'Add keyword' : 'Save keyword'}</></button>
    </div>
    {(inputError || error) && <small className="keyword-input-error" id="keyword-error" role="alert">{inputError || error}</small>}
    <div className="keyword-tags" aria-label="Configured keywords">
      {keywords.length ? keywords.map((keyword, index) => <span className="keyword-tag" key={`${keyword.toLocaleLowerCase()}-${index}`}>
        <span>{keyword}</span>
        <button type="button" disabled={disabled} onClick={() => edit(index)} aria-label={`Edit ${keyword}`} title={`Edit ${keyword}`}><Pencil size={12} /></button>
        <button type="button" disabled={disabled} onClick={() => onChange(keywords.filter((_, itemIndex) => itemIndex !== index))} aria-label={`Remove ${keyword}`} title={`Remove ${keyword}`}><X size={13} /></button>
      </span>) : <span className="keyword-tags-empty">No keyword rules yet. Add one above.</span>}
    </div>
  </div>
}
