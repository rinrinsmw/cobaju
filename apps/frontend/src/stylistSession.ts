import type { StylistResponse } from './api'

export interface ChatMessage {
  role: 'user' | 'ai'
  text?: string
  response?: StylistResponse
}

export interface StylistSession {
  version: 1
  messages: ChatMessage[]
  conversationTheme?: string
  updatedAt: string
}

export const STYLIST_SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000

export function getStylistSessionKey(userId: number) {
  return `cobaju:stylist-session:${userId}`
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Record<string, unknown>
  if (message.role !== 'user' && message.role !== 'ai') return false
  if (message.text !== undefined && typeof message.text !== 'string') return false
  if (message.response !== undefined && !isStylistResponse(message.response)) return false
  return typeof message.text === 'string' || message.response !== undefined
}

function isStylistResponse(value: unknown): value is StylistResponse {
  if (!value || typeof value !== 'object') return false
  const response = value as Record<string, unknown>
  return (response.status === 'recommendation' || response.status === 'redirected' || response.status === 'rejected')
    && typeof response.message === 'string'
    && Array.isArray(response.owned_items)
    && response.owned_items.every(item => {
      if (!item || typeof item !== 'object') return false
      const ownedItem = item as Record<string, unknown>
      return typeof ownedItem.item_id === 'number'
        && typeof ownedItem.category === 'string'
        && typeof ownedItem.reason === 'string'
    })
    && Array.isArray(response.missing_categories)
    && response.missing_categories.every(item => {
      if (!item || typeof item !== 'object') return false
      const missingItem = item as Record<string, unknown>
      return typeof missingItem.category === 'string' && typeof missingItem.guidance === 'string'
    })
}

function isStylistSession(value: unknown): value is StylistSession {
  if (!value || typeof value !== 'object') return false
  const session = value as Record<string, unknown>
  return session.version === 1
    && Array.isArray(session.messages)
    && session.messages.every(isChatMessage)
    && (session.conversationTheme === undefined || typeof session.conversationTheme === 'string')
    && typeof session.updatedAt === 'string'
}

export function loadStylistSession(userId: number, now = Date.now()): StylistSession | null {
  const key = getStylistSessionKey(userId)

  try {
    const saved = window.sessionStorage.getItem(key)
    if (!saved) return null

    const session: unknown = JSON.parse(saved)
    if (!isStylistSession(session)) {
      window.sessionStorage.removeItem(key)
      return null
    }

    const updatedAt = Date.parse(session.updatedAt)
    if (!Number.isFinite(updatedAt) || now - updatedAt > STYLIST_SESSION_MAX_AGE_MS) {
      window.sessionStorage.removeItem(key)
      return null
    }

    return session
  } catch {
    clearStylistSession(userId)
    return null
  }
}

export function saveStylistSession(
  userId: number,
  messages: ChatMessage[],
  now = Date.now(),
  conversationTheme?: string,
) {
  const session: StylistSession = {
    version: 1,
    messages,
    ...(conversationTheme ? { conversationTheme } : {}),
    updatedAt: new Date(now).toISOString(),
  }

  try {
    window.sessionStorage.setItem(getStylistSessionKey(userId), JSON.stringify(session))
  } catch {
    // A blocked or full browser storage area should not break the chat experience.
  }
}

export function clearStylistSession(userId: number) {
  try {
    window.sessionStorage.removeItem(getStylistSessionKey(userId))
  } catch {
    // The conversation can still reset in memory when browser storage is unavailable.
  }
}
