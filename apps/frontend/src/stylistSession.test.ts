import { describe, expect, it } from 'vitest'

import {
  STYLIST_SESSION_MAX_AGE_MS,
  getStylistSessionKey,
  loadStylistSession,
  saveStylistSession,
  type ChatMessage,
} from './stylistSession'

const messages: ChatMessage[] = [
  { role: 'ai', text: 'Welcome' },
  { role: 'user', text: 'Help me dress for dinner' },
]

describe('stylist session persistence', () => {
  it('stores and restores a versioned session for one user', () => {
    const now = Date.parse('2026-07-18T08:00:00.000Z')
    saveStylistSession(12, messages, now, 'Dinner')

    expect(loadStylistSession(12, now)).toEqual({
      version: 1,
      messages,
      conversationTheme: 'Dinner',
      updatedAt: '2026-07-18T08:00:00.000Z',
    })
    expect(loadStylistSession(99, now)).toBeNull()
  })

  it('continues to load existing sessions that do not have a theme', () => {
    const now = Date.parse('2026-07-18T08:00:00.000Z')
    window.sessionStorage.setItem(getStylistSessionKey(12), JSON.stringify({
      version: 1,
      messages,
      updatedAt: new Date(now).toISOString(),
    }))

    expect(loadStylistSession(12, now)?.messages).toEqual(messages)
    expect(loadStylistSession(12, now)?.conversationTheme).toBeUndefined()
  })

  it('discards a session older than 24 hours', () => {
    const savedAt = Date.parse('2026-07-17T08:00:00.000Z')
    saveStylistSession(12, messages, savedAt)

    const afterExpiry = savedAt + STYLIST_SESSION_MAX_AGE_MS + 1
    expect(loadStylistSession(12, afterExpiry)).toBeNull()
    expect(window.sessionStorage.getItem(getStylistSessionKey(12))).toBeNull()
  })

  it('discards malformed or unsupported saved data', () => {
    const key = getStylistSessionKey(12)
    window.sessionStorage.setItem(key, JSON.stringify({ version: 2, messages, updatedAt: new Date().toISOString() }))

    expect(loadStylistSession(12)).toBeNull()
    expect(window.sessionStorage.getItem(key)).toBeNull()
  })
})
