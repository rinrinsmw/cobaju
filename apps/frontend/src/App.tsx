import { useState, useEffect } from 'react'
import type { Page } from './data'
import TopNav from './components/TopNav'
import Dashboard from './components/Dashboard'
import Wardrobe from './components/Wardrobe'
import Upload from './components/Upload'
import Stylist from './components/Stylist'
import History from './components/History'

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [chatPrefill, setChatPrefill] = useState('')
  const [key, setKey] = useState(0)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  const navigate = (p: Page, prefill = '') => {
    setPage(p)
    setChatPrefill(prefill)
    setKey(k => k + 1)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const isDark = page === 'dashboard'

  return (
    <div style={{ minHeight: '100vh', background: '#f7f4ef' }}>
      <TopNav page={page} onNavigate={navigate} scrolled={scrolled} isDarkPage={isDark} />
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
