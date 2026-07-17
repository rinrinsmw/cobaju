import { useState, useEffect } from 'react'
import type { Page } from './data'
import TopNav from './components/TopNav'
import Dashboard from './components/Dashboard'
import Wardrobe from './components/Wardrobe'
import Upload from './components/Upload'
import Stylist from './components/Stylist'
import History from './components/History'
import AuthScreen from './components/AuthScreen'
import { useAuth } from './auth'

export default function App() {
  const { user, checking, logout } = useAuth()
  const hashPage = window.location.hash.slice(1) as Page
  const [page, setPage] = useState<Page>(['dashboard', 'wardrobe', 'upload', 'stylist', 'history'].includes(hashPage) ? hashPage : 'dashboard')
  const [chatPrefill, setChatPrefill] = useState('')
  const [key, setKey] = useState(0)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  useEffect(() => {
    const syncHash = () => {
      const nextPage = window.location.hash.slice(1) as Page
      if (['dashboard', 'wardrobe', 'upload', 'stylist', 'history'].includes(nextPage)) setPage(nextPage)
    }
    window.addEventListener('hashchange', syncHash)
    return () => window.removeEventListener('hashchange', syncHash)
  }, [])

  const navigate = (p: Page, prefill = '') => {
    window.location.hash = p
    setPage(p)
    setChatPrefill(prefill)
    setKey(k => k + 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const isDark = page === 'dashboard'

  if (checking) return <div style={{ minHeight: '100vh', background: '#100f0d', color: '#c9a96e', display: 'grid', placeItems: 'center' }}>Opening your wardrobe…</div>
  if (!user) return <AuthScreen />

  return (
    <div style={{ minHeight: '100vh', background: '#f7f4ef' }}>
      <TopNav page={page} onNavigate={navigate} scrolled={scrolled} isDarkPage={isDark} onLogout={logout} />
      <div key={key} className="page-enter">
        {page === 'dashboard' && <Dashboard onNavigate={navigate} />}
        {page === 'wardrobe' && <Wardrobe onNavigate={navigate} />}
        {page === 'upload' && <Upload onNavigate={navigate} />}
        {page === 'stylist' && <Stylist prefill={chatPrefill} />}
        {page === 'history' && <History onNavigate={navigate} />}
      </div>
    </div>
  )
}
