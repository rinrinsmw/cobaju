import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { apiRequest, getToken, type User } from './api'

interface AuthValue {
  user: User | null
  checking: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(Boolean(getToken()))

  useEffect(() => {
    if (!getToken()) return
    apiRequest<User>('/auth/me').then(setUser).catch(() => window.localStorage.removeItem('access_token')).finally(() => setChecking(false))
  }, [])

  const login = async (email: string, password: string) => {
    const result = await apiRequest<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    window.localStorage.setItem('access_token', result.access_token)
    setUser(await apiRequest<User>('/auth/me'))
  }
  const register = async (email: string, password: string) => {
    await apiRequest('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) })
    await login(email, password)
  }
  const logout = () => { window.localStorage.removeItem('access_token'); setUser(null) }

  return <AuthContext.Provider value={{ user, checking, login, register, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
