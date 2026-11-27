import { useState } from 'react'
import { Plus } from 'lucide-react'

const questions = [
  ['What is DM Karo?', 'DM Karo helps businesses automate Instagram and Facebook conversations, including comment replies, direct messages, lead capture, and inbox management.'],
  ['Do I need technical skills to set up automations?', 'No. The visual workflow builder is designed to help you create and manage automation workflows without writing code.'],
  ['Does DM Karo connect to Instagram and Facebook?', 'This landing page shows a product preview only. Live platform connections are not available in this frontend demo and would depend on supported platform APIs and permissions.'],
  ['What is included in the All Access plan?', 'The plan includes all listed features, unlimited automation workflows, Instagram and Facebook automation, the AI assistant, lead management, analytics, and the unified inbox.'],
  ['Are there any usage limits?', 'The plan is subject to a fair usage policy. Availability and limits may also depend on external platform APIs, permissions, and rate limits.'],
  ['Can I cancel my subscription?', 'The pricing shown is a product preview. Subscription management and payment processing are not implemented in this landing-page-only project.'],
]

export function FaqAccordion() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)
  return <div className="faq-list">{questions.map(([question, answer], index) => {
    const expanded = openIndex === index
    return <article className="faq-item" key={question}><button className="faq-question" type="button" aria-expanded={expanded} onClick={() => setOpenIndex(expanded ? null : index)}>{question}<Plus /></button><div className={`faq-answer ${expanded ? 'open' : ''}`} aria-hidden={!expanded}><p>{answer}</p></div></article>
  })}</div>
}
