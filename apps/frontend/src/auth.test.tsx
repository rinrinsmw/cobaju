import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest, ApiError, SESSION_EXPIRED_MESSAGE } from './api'
import { AuthProvider, useAuth } from './auth'
import AuthScreen from './components/AuthScreen'
import { getStylistSessionKey } from './stylistSession'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function AuthBoundary() {
  const { user, logout } = useAuth()
  return user ? <><p data-testid="authenticated-user">{user.email}</p><button onClick={logout}>Sign out</button></> : <AuthScreen />
}

async function renderAuthenticated(
  fetchMock: ReturnType<typeof vi.fn>,
): Promise<{ queryClient: QueryClient; root: Root }> {
  window.localStorage.setItem('access_token', 'valid-token')
  fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1, email: 'user@example.com' }))
  vi.stubGlobal('fetch', fetchMock)

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)

  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider><AuthBoundary /></AuthProvider>
      </QueryClientProvider>,
    )
  })

  expect(document.querySelector('[data-testid="authenticated-user"]')?.textContent).toBe('user@example.com')
  return { queryClient, root }
}

async function unmount(root: Root) {
  await act(async () => root.unmount())
}

describe('authentication screen', () => {
  it('explains Cobaju value before a visitor creates an account', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider><AuthBoundary /></AuthProvider>
        </QueryClientProvider>,
      )
    })

    expect(document.querySelector<HTMLInputElement>('input[name="email"]')?.autocomplete).toBe('email')
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.autocomplete).toBe('current-password')

    const showPasswordButton = [...document.querySelectorAll('button')]
      .find(element => element.textContent === 'Show')
    expect(showPasswordButton?.type).toBe('button')
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.type).toBe('password')
    await act(async () => showPasswordButton?.click())
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.type).toBe('text')
    expect(document.querySelector('button[aria-label="Hide password"]')?.getAttribute('aria-pressed')).toBe('true')

    const createAccountSwitch = [...document.querySelectorAll('button')]
      .find(element => element.textContent === 'New here? Create an account')
    expect(createAccountSwitch?.style.minHeight).toBe('44px')
    await act(async () => createAccountSwitch?.click())

    expect(document.body.textContent).toContain('Build outfits from clothes you already own.')
    expect(document.body.textContent).toContain('Upload your wardrobe and get personalized AI outfit recommendations.')
    expect(document.body.textContent).toContain('Private wardrobe · AI styling · No invented items')
    expect(document.body.textContent).toContain('Use at least 8 characters.')
    expect(document.querySelector('h1')?.classList.contains('auth-heading')).toBe(true)
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.autocomplete).toBe('new-password')
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.getAttribute('aria-describedby')).toBe('registration-password-help')
    expect(document.querySelector<HTMLInputElement>('input[name="password"]')?.type).toBe('password')

    await unmount(root)
  })
})

describe('centralized expired-session handling', () => {
  let mountedRoot: Root | undefined

  afterEach(async () => {
    if (mountedRoot) await unmount(mountedRoot)
    mountedRoot = undefined
    vi.unstubAllGlobals()
  })

  it('logs out, clears protected cache, and shows a friendly message after a protected 401', async () => {
    const fetchMock = vi.fn()
    const rendered = await renderAuthenticated(fetchMock)
    mountedRoot = rendered.root
    rendered.queryClient.setQueryData(['wardrobe'], [{ id: 12 }])
    window.sessionStorage.setItem(getStylistSessionKey(1), 'saved conversation')
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Could not validate credentials' }, 401))

    let requestError: unknown
    await act(async () => {
      try {
        await apiRequest('/wardrobe/items')
      } catch (error) {
        requestError = error
      }
    })

    expect(requestError).toBeInstanceOf(ApiError)
    expect((requestError as ApiError).message).toBe(SESSION_EXPIRED_MESSAGE)
    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(rendered.queryClient.getQueryData(['wardrobe'])).toBeUndefined()
    expect(window.sessionStorage.getItem(getStylistSessionKey(1))).toBeNull()
    expect(document.querySelector('[data-testid="authenticated-user"]')).toBeNull()
    expect(document.querySelector('[role="alert"]')?.textContent).toBe(SESSION_EXPIRED_MESSAGE)
    expect(document.body.textContent).toContain('Welcome back.')
  })

  it('clears the current user stylist session on explicit logout', async () => {
    const fetchMock = vi.fn()
    const rendered = await renderAuthenticated(fetchMock)
    mountedRoot = rendered.root
    window.sessionStorage.setItem(getStylistSessionKey(1), 'saved conversation')

    const signOut = [...document.querySelectorAll('button')].find(element => element.textContent === 'Sign out')
    await act(async () => signOut?.click())

    expect(window.sessionStorage.getItem(getStylistSessionKey(1))).toBeNull()
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it.each([400, 500])('keeps the authenticated session for a protected %s response', async status => {
    const fetchMock = vi.fn()
    const rendered = await renderAuthenticated(fetchMock)
    mountedRoot = rendered.root
    rendered.queryClient.setQueryData(['wardrobe'], [{ id: 12 }])
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'Request failed safely' }, status))

    await expect(apiRequest('/wardrobe/items')).rejects.toMatchObject({
      status,
      message: 'Request failed safely',
    })

    expect(window.localStorage.getItem('access_token')).toBe('valid-token')
    expect(rendered.queryClient.getQueryData(['wardrobe'])).toEqual([{ id: 12 }])
    expect(document.querySelector('[data-testid="authenticated-user"]')?.textContent).toBe('user@example.com')
    expect(document.body.textContent).not.toContain(SESSION_EXPIRED_MESSAGE)
  })

  it.each(['/auth/login', '/auth/register'])('does not expire the session when %s rejects credentials', async path => {
    window.localStorage.setItem('access_token', 'existing-token')
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'Authentication failed' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest(path, { method: 'POST', body: '{}' })).rejects.toMatchObject({
      status: 401,
      message: 'Authentication failed',
    })

    expect(window.localStorage.getItem('access_token')).toBe('existing-token')
  })
})
