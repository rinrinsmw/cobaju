import type { Page } from '../data'

interface Props {
  page: Page
  onNavigate: (p: Page) => void
  scrolled: boolean
  isDarkPage: boolean
  onLogout: () => void
}

const links: { id: Page; label: string }[] = [
  { id: 'wardrobe', label: 'Wardrobe' },
  { id: 'stylist', label: 'Stylist' },
  { id: 'history', label: 'Lookbook' },
]

export default function TopNav({ page, onNavigate, scrolled, isDarkPage, onLogout }: Props) {
  const onDarkHero = isDarkPage && !scrolled
  const textColor = onDarkHero ? 'rgba(255,255,255,0.85)' : '#1a1816'
  const hoverColor = onDarkHero ? '#fff' : '#1a1816'
  const bg = scrolled ? undefined : onDarkHero ? 'transparent' : undefined

  return (
    <header
      className={scrolled ? 'nav-blur' : ''}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        background: bg,
        transition: 'background 0.3s, border-color 0.3s',
        borderBottom: scrolled ? '1px solid rgba(0,0,0,0.06)' : '1px solid transparent',
      }}
    >
      <div style={{
        maxWidth: 1280,
        margin: '0 auto',
        padding: '0 32px',
        height: 64,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        {/* Logo */}
        <button
          onClick={() => onNavigate('dashboard')}
          style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 22,
            fontWeight: 700,
            color: textColor,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            letterSpacing: '-0.01em',
            transition: 'color 0.3s',
          }}
        >
          Cobaju
        </button>

        {/* Center links */}
        <nav className="desktop-nav" style={{ display: 'flex', gap: 36, alignItems: 'center' }}>
          {links.map(l => (
            <button
              key={l.id}
              onClick={() => onNavigate(l.id)}
              style={{
                fontFamily: 'DM Sans, sans-serif',
                fontSize: 13,
                fontWeight: page === l.id ? 600 : 400,
                color: page === l.id ? hoverColor : textColor,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                transition: 'color 0.3s, opacity 0.3s',
                opacity: page === l.id ? 1 : 0.7,
                paddingBottom: page === l.id ? '2px' : 0,
                borderBottom: page === l.id
                  ? `1px solid ${onDarkHero ? 'rgba(255,255,255,0.6)' : '#1a1816'}`
                  : '1px solid transparent',
              }}
            >
              {l.label}
            </button>
          ))}
        </nav>

        {/* Right CTA */}
        <div style={{ display: 'flex', gap: 8 }}><button
          onClick={() => onNavigate('upload')}
          style={{
            fontFamily: 'DM Sans, sans-serif',
            fontSize: 13,
            fontWeight: 500,
            letterSpacing: '0.02em',
            padding: '9px 20px',
            borderRadius: 999,
            cursor: 'pointer',
            transition: 'all 0.2s',
            background: onDarkHero ? 'rgba(255,255,255,0.12)' : '#1a1816',
            color: onDarkHero ? 'rgba(255,255,255,0.9)' : '#f7f4ef',
            border: onDarkHero ? '1px solid rgba(255,255,255,0.25)' : '1px solid #1a1816',
          }}
        >
          Add piece
        </button>
        <button onClick={onLogout} aria-label="Sign out" title="Sign out" style={{ padding: '8px 10px', border: 'none', background: 'transparent', color: textColor, cursor: 'pointer', fontSize: 18 }}>↗</button></div>
      </div>
    </header>
  )
}
