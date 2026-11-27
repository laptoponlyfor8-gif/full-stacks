export type SocialChannel = 'instagram' | 'facebook'

export type FaqItem = {
  question: string
  answer: string
}

export type DashboardNavItem = {
  label: string
  path: string
  icon: import('lucide-react').LucideIcon
  section: 'workspace' | 'manage'
}

export type DemoAutomation = {
  id: string
  name: string
  platform: 'Instagram' | 'Facebook'
  content: string
  keywords: string[]
  comments: number
  messages: number
  status: 'Active' | 'Paused'
}

export type DemoActivity = {
  id: string
  title: string
  detail: string
  time: string
  kind: 'comment' | 'message' | 'lead' | 'automation'
}

export type SocialPlatform = 'instagram' | 'facebook'

export type SocialAccountType = 'Business' | 'Creator' | 'Instagram Professional' | 'Facebook Page'

export type ConnectionStatus =
  | 'Not Connected'
  | 'Connecting'
  | 'Connected'
  | 'Expired'
  | 'Authorization Expired'
  | 'Connection Error'
  | 'Disconnected'

export type SocialAccount = {
  id: string
  platform: SocialPlatform
  accountName: string
  accountType: SocialAccountType
  profileImage: string | null
  connectionStatus: ConnectionStatus
  connectedAt: string | null
}

export type AutomationPlatform = 'Instagram' | 'Facebook'

export type AutomationContentType = 'Instagram Reel' | 'Instagram Post' | 'Facebook Post'

export type AutomationStatus = 'Draft' | 'Active' | 'Paused' | 'Needs setup'

export type KeywordMatchMethod = 'exact' | 'contains' | 'any-phrase'

export type CommentTriggerConfiguration = {
  keywords: string[]
  matchingMethod: KeywordMatchMethod
  keywordRulesEnabled: boolean
  ignoreAccountOwner: boolean
  ignoreDuplicateEvents: boolean
  ignoreCommentsWithoutKeywords: boolean
  preventRepeatedCommentAutomation: boolean
  publicReplyEnabled: boolean
  publicReplyVariations: string[]
  customPublicReply: string
  updatedAt: string
}

export type Automation = {
  id: string
  name: string
  platform: AutomationPlatform
  accountId: string
  accountName: string
  contentType: AutomationContentType
  postUrl: string
  triggerType?: 'comment' | 'direct_message'
  status: AutomationStatus
  commentTrigger?: CommentTriggerConfiguration
  privateReplyText?: string
  executions?: number
  sentMessages?: number
  failedMessages?: number
  createdAt: string
  updatedAt: string
}

export type AutomationDraftInput = Omit<Automation, 'id' | 'status' | 'createdAt' | 'updatedAt'>
