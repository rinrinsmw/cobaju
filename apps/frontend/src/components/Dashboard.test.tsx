import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Dashboard from './Dashboard'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function renderDashboard(root: Root, onNavigate = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <Dashboard onNavigate={onNavigate} />
      </QueryClientProvider>,
    )
    await new Promise(resolve => window.setTimeout(resolve, 0))
  })
}

async function waitForStat(label: string, expectedValue: string) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const labelElement = [...document.querySelectorAll('div')].find(
      element => element.textContent === label,
    )
    if (labelElement?.previousElementSibling?.textContent === expectedValue) return
    await act(async () => {
      await new Promise(resolve => window.setTimeout(resolve, 0))
    })
  }
  throw new Error(`Stat did not render: ${label} = ${expectedValue}`)
}

describe('Dashboard styling prompt', () => {
  let root: Root | undefined

  afterEach(async () => {
    if (root) await act(async () => root?.unmount())
    root = undefined
    vi.unstubAllGlobals()
  })

  it('requires a non-whitespace prompt before enabling Style me', async () => {
    const navigate = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/wardrobe/items' || path === '/api/recommendations') {
        return jsonResponse([])
      }
      throw new Error(`Unexpected request: ${path}`)
    }))
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await renderDashboard(root, navigate)

    const input = container.querySelector<HTMLInputElement>(
      'input[placeholder="Describe an occasion…"]',
    )
    const styleButton = [...container.querySelectorAll('button')].find(
      button => button.textContent?.includes('Style me'),
    )
    if (!input || !styleButton) throw new Error('Styling prompt did not render')

    expect(styleButton.disabled).toBe(true)
    await act(async () => styleButton.click())
    expect(navigate).not.toHaveBeenCalled()

    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      valueSetter?.call(input, '   ')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(styleButton.disabled).toBe(true)

    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      valueSetter?.call(input, '  Dinner party  ')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(styleButton.disabled).toBe(false)

    await act(async () => styleButton.click())
    expect(navigate).toHaveBeenCalledWith('stylist', 'Dinner party')
  })

  it('shows live wardrobe, weekly outfit, and utilisation statistics', async () => {
    const currentDate = new Date().toISOString()
    const previousMonth = new Date(Date.now() - 31 * 24 * 60 * 60 * 1000).toISOString()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/wardrobe/items') {
        return jsonResponse([
          { id: 1, processing_status: 'completed' },
          { id: 2, processing_status: 'completed' },
          { id: 3, processing_status: 'pending' },
        ])
      }
      if (path === '/api/recommendations') {
        return jsonResponse([
          { selected_item_ids: [1, 3], created_at: currentDate },
          { selected_item_ids: [1], created_at: currentDate },
          { selected_item_ids: [2], created_at: previousMonth },
        ])
      }
      throw new Error(`Unexpected request: ${path}`)
    }))
    const container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)

    await renderDashboard(root)

    await waitForStat('pieces in wardrobe', '3')
    await waitForStat('outfits this week', '2')
    await waitForStat('wardrobe utilised', '100%')
    expect(document.body.textContent).not.toContain('avg. outfit score')
  })
})
