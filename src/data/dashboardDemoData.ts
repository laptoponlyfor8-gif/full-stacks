import type { DemoActivity, DemoAutomation } from '../types'

export const demoAutomations: DemoAutomation[] = [
  { id: 'ig-welcome', name: 'Reel comment → Welcome DM', platform: 'Instagram', content: 'Summer collection Reel', keywords: ['INFO', 'LINK'], comments: 482, messages: 431, status: 'Active' },
  { id: 'fb-guide', name: 'Product guide delivery', platform: 'Facebook', content: 'New arrivals post', keywords: ['GUIDE'], comments: 296, messages: 274, status: 'Active' },
  { id: 'ig-giveaway', name: 'Giveaway entry response', platform: 'Instagram', content: 'Community giveaway', keywords: ['ENTER', 'WIN'], comments: 184, messages: 162, status: 'Paused' },
  { id: 'fb-pricing', name: 'Pricing request follow-up', platform: 'Facebook', content: 'Service overview post', keywords: ['PRICE'], comments: 129, messages: 113, status: 'Active' },
]

export const demoActivity: DemoActivity[] = [
  { id: 'activity-1', title: 'Welcome DM sent', detail: 'Reel comment → Welcome DM · Instagram', time: '2 min ago', kind: 'message' },
  { id: 'activity-2', title: 'New comment matched', detail: 'Keyword “INFO” · Summer collection Reel', time: '8 min ago', kind: 'comment' },
  { id: 'activity-3', title: 'New lead captured', detail: 'From Instagram automation · Demo data', time: '14 min ago', kind: 'lead' },
  { id: 'activity-4', title: 'Automation completed', detail: 'Product guide delivery · Facebook', time: '26 min ago', kind: 'automation' },
]

export const dashboardStats = [
  { label: 'Total Comments', value: '2,481', change: '+18.6%', trend: 'up' as const, icon: 'comments' },
  { label: 'Total DMs Sent', value: '1,936', change: '+12.4%', trend: 'up' as const, icon: 'messages' },
  { label: 'Active Automations', value: '8', change: '3 platforms', trend: 'neutral' as const, icon: 'automations' },
  { label: 'Successful Replies', value: '94.8%', change: '+2.1%', trend: 'up' as const, icon: 'success' },
  { label: 'Total Leads', value: '328', change: '+16.2%', trend: 'up' as const, icon: 'leads' },
  { label: 'Connected Accounts', value: '0', change: 'Demo mode', trend: 'neutral' as const, icon: 'accounts' },
]

export const activityChartData = [34, 49, 42, 63, 54, 72, 61, 81, 69, 92, 75, 88]
export const dmChartData = [32, 44, 38, 57, 48, 69, 63, 74, 67, 87, 78, 96]

export const moduleCopy: Record<string, { title: string; description: string }> = {
  automations: { title: 'My Automations', description: 'Review and organize your comment-to-DM workflows.' },
  create: { title: 'Create Automation', description: 'Build a workflow that turns audience engagement into a helpful conversation.' },
  accounts: { title: 'Connected Accounts', description: 'Manage your social channels. Connections are not enabled in this demo.' },
  comments: { title: 'Comments', description: 'Explore sample Instagram and Facebook comment activity.' },
  messages: { title: 'DM Messages', description: 'Review sample direct messages sent by your demo automations.' },
  inbox: { title: 'Unified Inbox', description: 'A preview of conversations from your connected social channels.' },
  leads: { title: 'Leads', description: 'Browse sample leads captured by your demo workflows.' },
  analytics: { title: 'Analytics', description: 'Understand the sample performance of your automations.' },
  ai: { title: 'AI Assistant', description: 'AI-assisted replies are a preview and are not connected in this demo.' },
  media: { title: 'Media Library', description: 'Organize content for future automation workflows.' },
  settings: { title: 'Settings', description: 'Manage workspace preferences for this frontend demo.' },
  support: { title: 'Help & Support', description: 'Find help for the DM Karo frontend preview.' },
}
