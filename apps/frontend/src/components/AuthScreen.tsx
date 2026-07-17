import { useState, type CSSProperties, type FormEvent } from 'react'
import { useAuth } from '../auth'

export default function AuthScreen() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setSubmitting(true)
    try { await (mode === 'login' ? login(email, password) : register(email, password)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Authentication failed.') }
    finally { setSubmitting(false) }
  }

  return <main style={{ minHeight: '100vh', background: '#100f0d', display: 'grid', placeItems: 'center', padding: 24 }}>
    <div style={{ width: 'min(440px, 100%)', background: '#f7f4ef', borderRadius: 10, padding: '42px 38px' }}>
      <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 28, fontWeight: 700, marginBottom: 6 }}>Cobaju</p>
      <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 36, lineHeight: 1.1, marginBottom: 12 }}>{mode === 'login' ? 'Welcome back.' : 'Build your wardrobe.'}</h1>
      <p style={{ color: '#6b6055', fontSize: 14, marginBottom: 28 }}>{mode === 'login' ? 'Sign in to open your private wardrobe.' : 'Create an account to save your first piece.'}</p>
      <form onSubmit={submit} style={{ display: 'grid', gap: 15 }}>
        <label style={{ fontSize: 12, color: '#6b6055' }}>Email<input style={inputStyle} type="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
        <label style={{ fontSize: 12, color: '#6b6055' }}>Password<input style={inputStyle} type="password" required minLength={8} value={password} onChange={event => setPassword(event.target.value)} /></label>
        {error && <p role="alert" style={{ color: '#9f3a32', fontSize: 13 }}>{error}</p>}
        <button disabled={submitting} style={primaryButton}>{submitting ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }} style={switchButton}>{mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}</button>
    </div>
  </main>
}

const inputStyle: CSSProperties = { display: 'block', width: '100%', marginTop: 7, padding: '12px 13px', border: '1px solid rgba(0,0,0,.14)', borderRadius: 6, background: 'white', font: 'inherit' }
const primaryButton: CSSProperties = { marginTop: 6, padding: 13, border: 0, borderRadius: 999, background: '#1a1816', color: '#f7f4ef', fontWeight: 600, cursor: 'pointer' }
const switchButton: CSSProperties = { width: '100%', marginTop: 18, border: 0, background: 'transparent', color: '#6b6055', fontSize: 13, cursor: 'pointer' }
