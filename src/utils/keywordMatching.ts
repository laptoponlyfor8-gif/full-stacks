import type { KeywordMatchMethod } from '../types'

function normalizeText(text: string): string {
  return text.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().replace(/\s+/g, ' ')
}

export function testKeywordComment(comment: string, keywords: string[], method: KeywordMatchMethod, enabled: boolean): string | null {
  if (!enabled) return null
  const normalizedComment = normalizeText(comment)
  if (!normalizedComment) return null
  return keywords.find((keyword) => {
    const normalizedKeyword = normalizeText(keyword)
    if (!normalizedKeyword) return false
    if (method === 'exact') return comment.trim().toLocaleLowerCase() === keyword.trim().toLocaleLowerCase()
    if (method === 'contains') return comment.toLocaleLowerCase().includes(keyword.toLocaleLowerCase())
    return ` ${normalizedComment} `.includes(` ${normalizedKeyword} `)
  }) ?? null
}
