import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import History from './History'

const savedLook = {
  id: 42,
  original_request: 'Gallery opening',
  selected_item_ids: [10],
  items: [{ item_id: 10, available: true, name: 'Blue Oxford', category: 'top', color: 'blue' }],
  explanation: 'A polished gallery look.',
  evaluation_score: 9.2,
  created_at: '2026-07-20T12:00:00Z',
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function button(label: string) {
  const match = [...document.querySelectorAll('button')].find(element => element.textContent?.includes(label))
  if (!match) throw new Error(`Button not found: ${label}. Body: ${document.body.textContent}`)
  return match as HTMLButtonElement
}

async function waitForElement<T extends Element>(selector: string): Promise<T> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const element = document.querySelector<T>(selector)
    if (element) return element
    await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 0)) })
  }
  throw new Error(`Element not found: ${selector}`)
}

describe('Lookbook recommendation cards', () => {
  let root: Root | undefined

  afterEach(async () => {
    if (root) await act(async () => root?.unmount())
    root = undefined
    window.localStorage.clear()
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('requires confirmation, removes the card, and leaves Wear Again working', async () => {
    window.localStorage.setItem('access_token', 'test-token')
    let deleted = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const path = String(input)
      if (path === '/api/recommendations' && (!options?.method || options.method === 'GET')) {
        return jsonResponse(deleted ? [] : [savedLook])
      }
      if (path === '/api/wardrobe/items/10/image') {
        return new Response('image bytes', { headers: { 'Content-Type': 'image/jpeg' } })
      }
      if (path === '/api/recommendations/42' && options?.method === 'DELETE') {
        deleted = true
        return new Response(null, { status: 204 })
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    class TestURL extends URL {}
    Object.defineProperties(TestURL, {
      createObjectURL: { value: vi.fn(() => 'blob:blue-oxford') },
      revokeObjectURL: { value: vi.fn() },
    })
    vi.stubGlobal('URL', TestURL)
    const onNavigate = vi.fn()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await act(async () => {
      root?.render(<QueryClientProvider client={queryClient}><History onNavigate={onNavigate} /></QueryClientProvider>)
    })
    await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 25)) })

    expect(document.body.textContent).not.toContain('9.2')
    expect(document.body.textContent).toContain('Blue Oxford')
    expect(document.body.textContent).not.toContain('A polished gallery look.')
    expect(document.body.textContent).not.toContain('New look')
    expect(button('Wear again')).not.toBeNull()
    expect(button('Delete')).not.toBeNull()

    const image = await waitForElement<HTMLImageElement>('img[alt="Blue Oxford"]')
    expect(image.src).toContain('blob:blue-oxford')
    expect(image.style.objectFit).toBe('cover')
    expect(image.parentElement?.title).toBe('Hover to view the full image')

    await act(async () => image.parentElement?.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })))
    expect(image.style.objectFit).toBe('contain')
    await act(async () => image.parentElement?.dispatchEvent(new MouseEvent('mouseout', { bubbles: true })))
    expect(image.style.objectFit).toBe('cover')

    await act(async () => button('Wear again').click())
    expect(onNavigate).toHaveBeenCalledWith('stylist', 'Gallery opening')

    await act(async () => button('Delete').click())
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(fetchMock).not.toHaveBeenCalledWith('/api/recommendations/42', expect.anything())

    await act(async () => button('Cancel').click())
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.body.textContent).toContain('Gallery opening')

    await act(async () => button('Delete').click())
    await act(async () => {
      button('Delete Look').click()
      await new Promise(resolve => window.setTimeout(resolve, 25))
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/recommendations/42',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(document.body.textContent).not.toContain('Gallery opening')
    expect(document.querySelector('[role="status"]')?.textContent).toContain('Look deleted')
  })
})
