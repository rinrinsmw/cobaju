import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Stylist from './Stylist'
import { getStylistSessionKey, saveStylistSession } from '../stylistSession'

vi.mock('../auth', () => ({ useAuth: () => ({ user: { id: 7, email: 'stylist@example.com' } }) }))

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function renderStylist(): Promise<Root> {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])))
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)

  await act(async () => {
    root.render(<QueryClientProvider client={queryClient}><Stylist /></QueryClientProvider>)
    await new Promise(resolve => window.setTimeout(resolve, 0))
  })
  return root
}

function button(label: string) {
  const match = [...document.querySelectorAll('button')].find(element => element.textContent?.includes(label))
  if (!match) throw new Error(`Button not found: ${label}`)
  return match as HTMLButtonElement
}

describe('Stylist session UI', () => {
  let root: Root | undefined

  afterEach(async () => {
    if (root) await act(async () => root?.unmount())
    root = undefined
    vi.unstubAllGlobals()
  })

  it('restores saved completed messages and clears them after confirmation', async () => {
    const savedAt = Date.now() - 60_000
    saveStylistSession(7, [
      { role: 'ai', text: 'Welcome back' },
      { role: 'user', text: 'An outfit for dinner' },
      { role: 'ai', text: 'Try your navy shirt.' },
    ], savedAt)
    root = await renderStylist()

    expect(document.body.textContent).toContain('An outfit for dinner')
    expect(document.body.textContent).toContain('Try your navy shirt.')
    expect(JSON.parse(window.sessionStorage.getItem(getStylistSessionKey(7)) ?? '{}').updatedAt).toBe(new Date(savedAt).toISOString())

    await act(async () => button('New Request').click())
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(document.body.textContent).toContain('Your current conversation will be cleared.')

    await act(async () => button('Start New Request').click())
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.body.textContent).not.toContain('An outfit for dinner')
    expect(document.body.textContent).toContain("Tell me where you're going")
    expect(window.sessionStorage.getItem(getStylistSessionKey(7))).toBeNull()
  })

  it('returns directly to the welcome state when the conversation is empty', async () => {
    root = await renderStylist()

    await act(async () => button('New Request').click())

    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(window.sessionStorage.getItem(getStylistSessionKey(7))).toBeNull()
  })

  it('returns a recommendation after the user manually sends a request', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input)
      if (path === '/api/wardrobe/items') return jsonResponse([])
      if (path === '/api/chat/recommendations' && options?.method === 'POST') {
        return jsonResponse({
          status: 'recommendation',
          message: 'Wear your blue shirt with tailored trousers.',
          owned_items: [],
          missing_categories: [],
        })
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root?.render(<QueryClientProvider client={queryClient}><Stylist /></QueryClientProvider>)
      await new Promise(resolve => window.setTimeout(resolve, 0))
    })

    const input = container.querySelector<HTMLInputElement>('input[placeholder="Describe the occasion or look…"]')
    if (!input) throw new Error('Stylist input did not render')
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      valueSetter?.call(input, 'Help me dress for an interview')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      button('Send').click()
      await new Promise(resolve => window.setTimeout(resolve, 0))
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/recommendations',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ message: 'Help me dress for an interview' }),
      }),
    )
    expect(document.body.textContent).toContain('Wear your blue shirt with tailored trousers.')
  })
})
