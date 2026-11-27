import { Activity, Bot, Camera, ChartNoAxesCombined, ContactRound, GitBranch, Inbox, MessageCircle, MessageSquareText, ShieldCheck, Tags, UsersRound } from 'lucide-react'

const features = [
  { icon: MessageCircle, title: 'Comment-to-DM Automation', text: 'Turn post and Reel comments into timely, personal conversations.', tone: 'blue' },
  { icon: Camera, title: 'Instagram DM Automation', text: 'Welcome new followers and respond to common questions around the clock.', tone: 'violet' },
  { icon: MessageSquareText, title: 'Facebook Messenger Automation', text: 'Keep Facebook conversations moving with helpful automated replies.', tone: 'blue' },
  { icon: Bot, title: 'AI Chatbot', text: 'Give every conversation a helpful first response with an AI assistant.', tone: 'mint' },
  { icon: Tags, title: 'Keyword Automation', text: 'Send the right reply when people comment with a word or phrase.', tone: 'coral' },
  { icon: Activity, title: 'Story Automation', text: 'Start a conversation when someone replies to your Instagram story.', tone: 'violet' },
  { icon: UsersRound, title: 'Lead Generation', text: 'Capture interested people and turn engagement into qualified leads.', tone: 'mint' },
  { icon: Inbox, title: 'Unified Inbox', text: 'Bring conversations together in one clear, manageable inbox.', tone: 'blue' },
  { icon: GitBranch, title: 'Visual Workflow Builder', text: 'Build clear, flexible conversation flows without writing code.', tone: 'violet' },
  { icon: ChartNoAxesCombined, title: 'Analytics Dashboard', text: 'Understand engagement, delivery, and lead performance at a glance.', tone: 'mint' },
  { icon: ShieldCheck, title: 'AI Comment Moderation', text: 'Keep comment sections healthier with automated moderation tools.', tone: 'coral' },
  { icon: ContactRound, title: 'Customer Management', text: 'Keep useful context and contact details close to every conversation.', tone: 'blue' },
]

export function FeatureGrid() {
  return <div className="features-grid">{features.map(({ icon: Icon, title, text, tone }) => <article className="feature-card" key={title}><span className={`feature-icon ${tone}`}><Icon /></span><h3>{title}</h3><p>{text}</p></article>)}</div>
}
