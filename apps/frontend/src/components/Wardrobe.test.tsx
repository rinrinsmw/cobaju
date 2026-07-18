import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import Wardrobe from './Wardrobe'

const item = {
  id: 7,
  name: 'Blue Shirt',
  category: 'top' as const,
  color: 'blue',
  description: 'A blue shirt',
  original_image_path: '1/blue-shirt.jpg',
  analysis_completed: true,
  processing_status: 'completed' as const,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function render(root: Root, queryClient: QueryClient, child: ReactNode) {
  await act(async () => {
    root.render(<QueryClientProvider client={queryClient}>{child}</QueryClientProvider>)
    await new Promise(resolve => window.setTimeout(resolve, 0))
  })
}

async function waitForImage(source: string): Promise<HTMLImageElement> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await act(async () => new Promise(resolve => window.setTimeout(resolve, 10)))
    const image = document.querySelector<HTMLImageElement>('img[alt="Blue Shirt"]')
    if (image?.src.includes(source)) return image
  }
  throw new Error(`Image did not render with source: ${source}`)
}

describe('Wardrobe item image lifecycle', () => {
  let mountedRoot: Root | undefined

  afterEach(async () => {
    if (mountedRoot) await act(async () => mountedRoot?.unmount())
    mountedRoot = undefined
    vi.unstubAllGlobals()
  })

  it('caches the Blob and creates a fresh active object URL after remount', async () => {
    window.localStorage.setItem('access_token', 'valid-token')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/wardrobe/items') return jsonResponse([item])
      if (path === `/api/wardrobe/items/${item.id}/image`) {
        return new Response('image bytes', { headers: { 'Content-Type': 'image/jpeg' } })
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const revokedUrls = new Set<string>()
    const createObjectURL = vi.fn()
      .mockReturnValueOnce('blob:first-mount')
      .mockReturnValueOnce('blob:second-mount')
    const revokeObjectURL = vi.fn((url: string) => revokedUrls.add(url))
    class TestURL extends URL {}
    Object.defineProperties(TestURL, {
      createObjectURL: { value: createObjectURL },
      revokeObjectURL: { value: revokeObjectURL },
    })
    vi.stubGlobal('URL', TestURL)

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    const container = document.createElement('div')
    document.body.appendChild(container)
    mountedRoot = createRoot(container)

    await render(mountedRoot, queryClient, <Wardrobe onNavigate={() => undefined} />)
    expect((await waitForImage('blob:first-mount')).src).toContain('blob:first-mount')

    const cachedImage = queryClient.getQueryData(['item-image', item.id])
    expect(Object.prototype.toString.call(cachedImage)).toBe('[object Blob]')
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith(`/${item.id}/image`))).toHaveLength(1)

    await render(mountedRoot, queryClient, <div>Another page</div>)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first-mount')
    expect(revokedUrls.has('blob:first-mount')).toBe(true)

    await render(mountedRoot, queryClient, <Wardrobe onNavigate={() => undefined} />)
    expect((await waitForImage('blob:second-mount')).src).toContain('blob:second-mount')

    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith(`/${item.id}/image`))).toHaveLength(1)
    expect(createObjectURL).toHaveBeenCalledTimes(2)
    expect(revokedUrls.has('blob:second-mount')).toBe(false)
  })
})
