import { useState, type CSSProperties, type FormEvent } from 'react'
import { useAuth } from '../auth'

export default function AuthScreen() {
  const { login, register, sessionMessage } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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
      <h1 className="auth-heading" style={{ fontFamily: "'Playfair Display', serif", lineHeight: 1.1, marginBottom: 12 }}>{mode === 'login' ? 'Welcome back.' : 'Build outfits from clothes you already own.'}</h1>
      <p style={{ color: '#6b6055', fontSize: 14, marginBottom: mode === 'login' ? 28 : 10 }}>{mode === 'login' ? 'Sign in to open your private wardrobe.' : 'Upload your wardrobe and get personalized AI outfit recommendations.'}</p>
      {mode === 'register' && <p style={{ color: '#8b7d70', fontSize: 12, lineHeight: 1.5, marginBottom: 20 }}>Private wardrobe · AI styling · No invented items</p>}
      {sessionMessage && <p role="alert" style={{ color: '#9f3a32', fontSize: 13, marginBottom: 18 }}>{sessionMessage}</p>}
      <form onSubmit={submit} style={{ display: 'grid', gap: 15 }}>
        <label style={{ fontSize: 12, color: '#6b6055' }}>Email<input style={inputStyle} type="email" name="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} /></label>
        <div style={{ fontSize: 12, color: '#6b6055' }}>
          <label htmlFor="auth-password">Password</label>
          <div style={{ position: 'relative', marginTop: 7 }}>
            <input
              id="auth-password"
              style={{ ...inputStyle, marginTop: 0, paddingRight: 72 }}
              type={showPassword ? 'text' : 'password'}
              name="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              aria-describedby={mode === 'register' ? 'registration-password-help' : undefined}
              required
              minLength={8}
              value={password}
              onChange={event => setPassword(event.target.value)}
            />
            <button
              type="button"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              aria-pressed={showPassword}
              onClick={() => setShowPassword(!showPassword)}
              style={passwordToggleButton}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          {mode === 'register' && <span id="registration-password-help" style={{ display: 'block', marginTop: 6 }}>Use at least 8 characters.</span>}
        </div>
        {error && <p role="alert" style={{ color: '#9f3a32', fontSize: 13 }}>{error}</p>}
        <button disabled={submitting} style={primaryButton}>{submitting ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setShowPassword(false); setError('') }} style={switchButton}>{mode === 'login' ? 'New here? Create an account' : 'Already have an account? Sign in'}</button>
    </div>
  </main>
}

const inputStyle: CSSProperties = { display: 'block', width: '100%', marginTop: 7, padding: '12px 13px', border: '1px solid rgba(0,0,0,.14)', borderRadius: 6, background: 'white', font: 'inherit' }
const passwordToggleButton: CSSProperties = { position: 'absolute', top: 0, right: 0, height: '100%', minWidth: 60, padding: '0 12px', border: 0, background: 'transparent', color: '#6b6055', fontSize: 12, fontWeight: 600, cursor: 'pointer' }
const primaryButton: CSSProperties = { marginTop: 6, padding: 13, border: 0, borderRadius: 999, background: '#1a1816', color: '#f7f4ef', fontWeight: 600, cursor: 'pointer' }
const switchButton: CSSProperties = { width: '100%', minHeight: 44, marginTop: 18, padding: '10px 8px', border: 0, background: 'transparent', color: '#6b6055', fontSize: 13, cursor: 'pointer' }
