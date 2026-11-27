import { useMemo, useState } from 'react'
import { Check, CircleX, FlaskConical, MessageSquareText, Sparkles } from 'lucide-react'
import type { KeywordMatchMethod } from '../../types'
import { testKeywordComment } from '../../utils/keywordMatching'

type Props = {
  keywords: string[]
  method: KeywordMatchMethod
  enabled: boolean
  publicReplyEnabled: boolean
  publicReply: string
  ignoreAccountOwner: boolean
  ignoreDuplicateEvents: boolean
  ignoreCommentsWithoutKeywords: boolean
  preventRepeatedCommentAutomation: boolean
}

export function CommentTriggerTester({ keywords, method, enabled, publicReplyEnabled, publicReply, ignoreAccountOwner, ignoreDuplicateEvents, ignoreCommentsWithoutKeywords, preventRepeatedCommentAutomation }: Props) {
  const [comment, setComment] = useState('Please send me the LINK.')
  const [fromOwner, setFromOwner] = useState(false)
  const [duplicateEvent, setDuplicateEvent] = useState(false)
  const [duplicate, setDuplicate] = useState(false)
  const result = useMemo(() => {
    const matchedKeyword = testKeywordComment(comment, keywords, method, enabled)
    const blockedReason = fromOwner && ignoreAccountOwner
      ? 'Ignored because the test comment is marked as coming from the connected account owner.'
      : duplicateEvent && ignoreDuplicateEvents
        ? 'Ignored because this test event is marked as a duplicate notification.'
      : duplicate && preventRepeatedCommentAutomation
        ? 'Ignored because this test comment is marked as already processed.'
        : !matchedKeyword && enabled && ignoreCommentsWithoutKeywords
          ? 'Ignored because no configured keyword matched this comment.'
        : ''
    return { matchedKeyword, blockedReason, triggered: Boolean(matchedKeyword) && !blockedReason }
  }, [comment, keywords, method, enabled, fromOwner, ignoreAccountOwner, duplicateEvent, ignoreDuplicateEvents, ignoreCommentsWithoutKeywords, duplicate, preventRepeatedCommentAutomation])

  return <section className="dashboard-panel comment-trigger-tester">
    <div className="dashboard-panel-heading"><div><span className="dashboard-section-kicker">LOCAL TEST · NO PLATFORM CONNECTION</span><h2><FlaskConical size={17} /> Trigger preview</h2><p>Try a comment to see how this demo configuration responds.</p></div><span className="dashboard-demo-pill-small">DEMO ONLY</span></div>
    <label className="trigger-test-comment-label" htmlFor="trigger-test-comment">Sample comment</label>
    <textarea id="trigger-test-comment" rows={3} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Type a sample comment, e.g. Please send me the LINK." />
    <div className="trigger-test-options"><label><input type="checkbox" checked={fromOwner} onChange={(event) => setFromOwner(event.target.checked)} /> Test as account owner</label><label><input type="checkbox" checked={duplicateEvent} onChange={(event) => setDuplicateEvent(event.target.checked)} /> Test as duplicate event</label><label><input type="checkbox" checked={duplicate} onChange={(event) => setDuplicate(event.target.checked)} /> Test as already processed</label></div>
    <div className={`trigger-test-result${result.triggered ? ' matched' : ''}`} role="status" aria-live="polite">
      <span className="trigger-result-icon">{result.triggered ? <Check size={17} /> : <CircleX size={17} />}</span>
      <div className="trigger-result-content"><strong>{result.triggered ? 'Trigger matched' : 'No trigger'}</strong>
        <dl><div><dt>Detected keyword</dt><dd>{result.matchedKeyword ?? 'None'}</dd></div><div><dt>Matching rule</dt><dd>{method === 'exact' ? 'Exact Match' : method === 'contains' ? 'Contains Keyword' : 'Any Matching Phrase'}</dd></div><div><dt>Trigger result</dt><dd>{result.blockedReason || (result.triggered ? 'Matched and eligible in this local demo.' : enabled ? 'No configured keyword matched this comment.' : 'Keyword rules are disabled.')}</dd></div><div><dt>Expected next action</dt><dd>{result.triggered ? publicReplyEnabled ? `Preview public reply${publicReply ? `: “${publicReply}”` : ' and continue to DM setup'}` : 'Continue to DM setup; public reply is off' : 'No action'}</dd></div></dl>
      </div>
    </div>
    <p className="trigger-demo-caveat"><Sparkles size={13} /> This is a local simulation only. DM Karo does not read Instagram or Facebook comments.</p>
    <div className="trigger-test-examples"><span><MessageSquareText size={13} /> Try: <button type="button" onClick={() => setComment('LINK')}>LINK</button><button type="button" onClick={() => setComment('Send LINK')}>Send LINK</button><button type="button" onClick={() => setComment('I need the linktree')}>I need the linktree</button></span></div>
  </section>
}
