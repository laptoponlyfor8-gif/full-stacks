import { Check, CircleDot } from 'lucide-react'
import type { KeywordMatchMethod } from '../../types'

const methods: { id: KeywordMatchMethod; title: string; description: string; example: string }[] = [
  { id: 'exact', title: 'Exact Match', description: 'The entire comment must be the keyword or phrase (case-insensitive).', example: 'LINK matches “link”, not “send link”' },
  { id: 'contains', title: 'Contains Keyword', description: 'Triggers when the comment contains a keyword anywhere in its text.', example: 'LINK matches “Please send me the link.”' },
  { id: 'any-phrase', title: 'Any Matching Phrase', description: 'Matches a whole configured word or phrase, not a partial word.', example: 'LINK matches “send link”, not “linktree”' },
]

export function KeywordMatchMethodPicker({ value, onChange, disabled }: { value: KeywordMatchMethod; onChange: (method: KeywordMatchMethod) => void; disabled: boolean }) {
  return <fieldset className="keyword-method-picker" disabled={disabled}>
    <legend className="sr-only">Keyword matching method</legend>
    {methods.map((method) => {
      const selected = value === method.id
      return <label className={`keyword-method-card${selected ? ' selected' : ''}`} key={method.id}>
        <input type="radio" name="keyword-match-method" value={method.id} checked={selected} onChange={() => onChange(method.id)} />
        <span className="keyword-method-radio">{selected ? <Check size={12} /> : <CircleDot size={12} />}</span>
        <span className="keyword-method-copy"><strong>{method.title}</strong><small>{method.description}</small><em>{method.example}</em></span>
      </label>
    })}
  </fieldset>
}
