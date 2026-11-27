import type { AutomationContentType, AutomationPlatform } from '../types'

export type AutomationFields = {
  name: string
  platform: AutomationPlatform | ''
  accountId: string
  contentType: AutomationContentType | ''
  postUrl: string
}

export type AutomationFieldErrors = Partial<Record<keyof AutomationFields, string>>

export function validatePostUrl(value: string, platform: AutomationPlatform | ''): string {
  if (!value.trim()) return 'Paste the Reel or Post URL to continue.'

  let url: URL
  try {
    url = new URL(value.trim())
  } catch {
    return 'Enter a valid full URL starting with https://.'
  }

  if (url.protocol !== 'https:') return 'Use a secure HTTPS link.'
  const host = url.hostname.toLowerCase().replace(/^www\./, '')

  if (platform === 'Instagram') {
    if (host !== 'instagram.com' && host !== 'm.instagram.com') return 'This URL is not from Instagram. Select Instagram or enter an Instagram URL.'
    if (!/^\/(reel|p)\/[A-Za-z0-9_-]+\/?$/.test(url.pathname)) return 'Use a supported Instagram Reel (/reel/…) or Post (/p/…) URL.'
    return ''
  }

  if (platform === 'Facebook') {
    if (host !== 'facebook.com' && host !== 'm.facebook.com' && host !== 'web.facebook.com') return 'This URL is not from Facebook. Select Facebook or enter a Facebook URL.'
    if (url.pathname === '/' || url.pathname.length < 2) return 'Enter a link to a specific Facebook post.'
    return ''
  }

  return 'Select a social platform before validating the URL.'
}

export function validateAutomationFields(fields: AutomationFields): AutomationFieldErrors {
  const errors: AutomationFieldErrors = {}
  if (!fields.name.trim()) errors.name = 'Enter an automation name.'
  if (!fields.platform) errors.platform = 'Select Instagram or Facebook.'
  if (!fields.accountId) errors.accountId = 'Select a connected social account.'
  if (!fields.contentType) errors.contentType = 'Select a content type.'
  if (fields.platform === 'Instagram' && fields.contentType === 'Facebook Post') errors.contentType = 'Choose an Instagram Reel or Instagram Post for Instagram.'
  if (fields.platform === 'Facebook' && fields.contentType !== 'Facebook Post' && fields.contentType !== '') errors.contentType = 'Choose a Facebook Post for Facebook.'
  const urlError = validatePostUrl(fields.postUrl, fields.platform)
  if (urlError) errors.postUrl = urlError
  return errors
}
