import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  apiRequest,
  getToken,
  SESSION_EXPIRED_EVENT,
  SESSION_EXPIRED_MESSAGE,
  type User,
} from './api'
import { clearStylistSession } from './stylistSession'

interface AuthValue {
  user: User | null
  checking: boolean
  sessionMessage: string
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(Boolean(getToken()))
  const [sessionMessage, setSessionMessage] = useState('')

  useEffect(() => {
    const handleSessionExpired = () => {
      if (user) clearStylistSession(user.id)
      setUser(null)
      setChecking(false)
      setSessionMessage(SESSION_EXPIRED_MESSAGE)
      queryClient.clear()
    }

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired)
  }, [queryClient, user])

  useEffect(() => {
    if (!getToken()) return
    apiRequest<User>('/auth/me').then(setUser).catch(() => undefined).finally(() => setChecking(false))
  }, [])

  const login = async (email: string, password: string) => {
    const result = await apiRequest<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    window.localStorage.setItem('access_token', result.access_token)
    setUser(await apiRequest<User>('/auth/me'))
    setSessionMessage('')
  }
  const register = async (email: string, password: string) => {
    await apiRequest('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) })
    await login(email, password)
  }
  const logout = () => {
    if (user) clearStylistSession(user.id)
    window.localStorage.removeItem('access_token')
    setUser(null)
    setSessionMessage('')
    queryClient.clear()
  }

  return <AuthContext.Provider value={{ user, checking, sessionMessage, login, register, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
