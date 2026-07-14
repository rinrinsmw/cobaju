import { useState } from 'react'
import type { Page } from '../data'

interface Props {
  onNavigate: (p: Page, prefill?: string) => void
}

/* Scattered collage photo positions — mimics Whering's organic mood board */
const collagePhotos = [
  {
    url: 'https://images.unsplash.com/flagged/photo-1570733117311-d990c3816c47?w=500&h=640&fit=crop&auto=format',
    alt: 'Two women in white shirts',
    style: { top: '8%', right: '5%', width: 220, height: 290, rotate: '2deg' },
  },
  {
    url: 'https://images.unsplash.com/photo-1662532577856-e8ee8b138a8b?w=400&h=560&fit=crop&auto=format',
    alt: 'Red dress editorial',
    style: { top: '38%', right: '14%', width: 170, height: 230, rotate: '-3deg' },
  },
  {
    url: 'https://images.unsplash.com/photo-1613915617430-8ab0fd7c6baf?w=360&h=480&fit=crop&auto=format',
    alt: 'Black blazer scarf',
    style: { top: '22%', right: '28%', width: 140, height: 190, rotate: '1.5deg' },
  },
]

const features = [
  { label: 'Outfit generation', desc: 'From your actual wardrobe, not a wishlist.' },
  { label: 'AI analysis', desc: 'Every item tagged automatically on upload.' },
  { label: 'Style memory', desc: 'Learns what works for you over time.' },
]

export default function Dashboard({ onNavigate }: Props) {
  const [query, setQuery] = useState('')

  const handleAsk = () => {
    onNavigate('stylist', query.trim() || 'Smart casual outfit')
  }

  return (
    <div>
      {/* ── HERO — dark full-bleed ──────────────────────────────────── */}
      <section style={{
        minHeight: '100vh',
        background: '#100f0d',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        paddingBottom: 80,
      }}>
        {/* Ambient gradient */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse 70% 60% at 30% 60%, rgba(180,140,90,0.12) 0%, transparent 70%)',
          pointerEvents: 'none',
        }} />

        {/* Organic photo collage — top-right */}
        {collagePhotos.map((p, i) => (
          <div key={i} className="img-zoom" style={{
            position: 'absolute',
            top: p.style.top,
            right: p.style.right,
            width: p.style.width,
            height: p.style.height,
            transform: `rotate(${p.style.rotate})`,
            borderRadius: 4,
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
            zIndex: 2,
          }}>
            <img src={p.url} alt={p.alt} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
          </div>
        ))}

        {/* Small decorative label */}
        <div style={{
          position: 'absolute', top: 100, left: 60,
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.3)',
        }}>
          AI Personal Stylist — 2025
        </div>

        {/* Hero text */}
        <div style={{ position: 'relative', zIndex: 3, padding: '0 60px' }}>
          <p style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 12,
            letterSpacing: '0.16em', textTransform: 'uppercase',
            color: '#c9a96e', marginBottom: 24,
          }}>
            Your wardrobe, rediscovered
          </p>

          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 'clamp(52px, 7vw, 96px)',
            fontWeight: 700,
            lineHeight: 1.02,
            letterSpacing: '-0.02em',
            color: '#f0ece4',
            maxWidth: 700,
            marginBottom: 32,
          }}>
            Love what<br />
            you already<br />
            <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>own.</em>
          </h1>

          <p style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 17,
            lineHeight: 1.65, color: 'rgba(240,236,228,0.55)',
            maxWidth: 420, marginBottom: 48,
          }}>
            Cobaju builds outfits from the clothes in your wardrobe.
            No shopping required.
          </p>

          {/* Prompt bar */}
          <div style={{
            display: 'flex', gap: 0, maxWidth: 520,
            background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.14)',
            borderRadius: 999,
            padding: '6px 6px 6px 22px',
            backdropFilter: 'blur(10px)',
          }}>
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAsk()}
              placeholder="Describe an occasion…"
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                fontFamily: 'DM Sans, sans-serif', fontSize: 14,
                color: 'rgba(255,255,255,0.85)',
                paddingRight: 12,
              }}
            />
            <button onClick={handleAsk} style={{
              fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 600,
              background: '#f0ece4', color: '#100f0d',
              border: 'none', borderRadius: 999,
              padding: '10px 22px', cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'transform 0.15s',
            }}>
              Style me →
            </button>
          </div>

          {/* Quick chips */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
            {['Interview tomorrow', 'Weekend brunch', 'First date', 'Gallery opening'].map(p => (
              <button key={p}
                onClick={() => { setQuery(p); onNavigate('stylist', p) }}
                style={{
                  fontFamily: 'DM Sans, sans-serif', fontSize: 12,
                  color: 'rgba(255,255,255,0.55)',
                  background: 'transparent', border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: 999, padding: '6px 14px', cursor: 'pointer',
                  transition: 'border-color 0.2s, color 0.2s',
                }}>
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* Bottom fade into cream */}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0, height: 120,
          background: 'linear-gradient(to bottom, transparent, #100f0d)',
          pointerEvents: 'none', zIndex: 1,
        }} />
      </section>

      {/* ── STATS BAR ───────────────────────────────────────────────── */}
      <section style={{
        background: '#1a1816',
        padding: '28px 60px',
        display: 'flex', gap: 60, alignItems: 'center',
        justifyContent: 'center',
        flexWrap: 'wrap',
      }}>
        {[
          { n: '11', label: 'pieces in wardrobe' },
          { n: '3', label: 'outfits this week' },
          { n: '9.4', label: 'avg. outfit score' },
          { n: '73%', label: 'wardrobe utilised' },
        ].map(s => (
          <div key={s.label} style={{ textAlign: 'center' }}>
            <div style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: 40, fontWeight: 700,
              color: '#c9a96e', lineHeight: 1,
            }}>{s.n}</div>
            <div style={{
              fontFamily: 'DM Sans, sans-serif', fontSize: 12,
              letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.4)', marginTop: 6,
            }}>{s.label}</div>
          </div>
        ))}
      </section>

      {/* ── WARDROBE PREVIEW — light section ────────────────────────── */}
      <section style={{ background: '#f7f4ef', padding: '100px 60px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 80, alignItems: 'center' }}>
            <div>
              <p style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                letterSpacing: '0.16em', textTransform: 'uppercase',
                color: '#a09080', marginBottom: 20,
              }}>Your wardrobe</p>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 'clamp(36px, 4vw, 58px)',
                fontWeight: 700, lineHeight: 1.08,
                letterSpacing: '-0.02em', color: '#1a1816',
                marginBottom: 24,
              }}>
                Every piece,<br />
                <em style={{ fontStyle: 'italic' }}>finally seen.</em>
              </h2>
              <p style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 16,
                lineHeight: 1.7, color: '#6b6055',
                maxWidth: 360, marginBottom: 40,
              }}>
                Upload your clothing once. Cobaju handles categorisation, colour-matching, and occasion tagging automatically.
              </p>
              <button onClick={() => onNavigate('wardrobe')} style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 13,
                fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
                color: '#1a1816', background: 'transparent',
                border: '1px solid #1a1816', borderRadius: 999,
                padding: '12px 28px', cursor: 'pointer',
                transition: 'background 0.2s, color 0.2s',
              }}
                onMouseEnter={e => {
                  (e.target as HTMLButtonElement).style.background = '#1a1816';
                  (e.target as HTMLButtonElement).style.color = '#f7f4ef'
                }}
                onMouseLeave={e => {
                  (e.target as HTMLButtonElement).style.background = 'transparent';
                  (e.target as HTMLButtonElement).style.color = '#1a1816'
                }}
              >
                Open wardrobe →
              </button>
            </div>

            {/* Photo grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[
                { url: 'https://images.unsplash.com/photo-1612731486606-2614b4d74921?w=400&h=520&fit=crop&auto=format', span: true },
                { url: 'https://images.unsplash.com/photo-1578432156830-0ca0d7913b7f?w=400&h=260&fit=crop&auto=format', span: false },
                { url: 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=260&fit=crop&auto=format', span: false },
                { url: 'https://images.unsplash.com/photo-1580478491436-fd6a937acc9e?w=400&h=260&fit=crop&auto=format', span: false },
              ].map((img, i) => (
                <div key={i} className="img-zoom" style={{
                  borderRadius: 8,
                  overflow: 'hidden',
                  gridRow: img.span ? 'span 2' : undefined,
                  background: '#e8e0d4',
                }}>
                  <img src={img.url} alt="wardrobe" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', minHeight: img.span ? 280 : 140 }} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS — dark section ─────────────────────────────── */}
      <section style={{ background: '#1a1816', padding: '100px 60px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          <p style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 11,
            letterSpacing: '0.16em', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.3)', marginBottom: 20, textAlign: 'center',
          }}>How Cobaju works</p>
          <h2 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 'clamp(34px, 4vw, 52px)',
            fontWeight: 700, lineHeight: 1.1,
            color: '#f0ece4', textAlign: 'center',
            marginBottom: 64,
          }}>
            Three steps to a perfect outfit
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 48 }}>
            {[
              {
                n: '01', title: 'Build your wardrobe',
                desc: 'Upload photos of your clothing. AI tags each piece with category, colour, and occasion.',
                img: 'https://images.unsplash.com/photo-1731589802397-6a1088d63630?w=500&h=380&fit=crop&auto=format',
              },
              {
                n: '02', title: 'Describe your day',
                desc: 'Tell Cobaju where you\'re going. It searches only what you own.',
                img: 'https://images.unsplash.com/photo-1559127452-cb4ef7888fa1?w=500&h=380&fit=crop&auto=format',
              },
              {
                n: '03', title: 'Wear with confidence',
                desc: 'Get a scored outfit with reasons. Save it to your lookbook.',
                img: 'https://images.unsplash.com/photo-1613915617430-8ab0fd7c6baf?w=500&h=380&fit=crop&auto=format',
              },
            ].map(step => (
              <div key={step.n}>
                <div className="img-zoom" style={{ borderRadius: 6, overflow: 'hidden', marginBottom: 24, background: '#2a2820' }}>
                  <img src={step.img} alt={step.title} style={{ width: '100%', height: 260, objectFit: 'cover', display: 'block', opacity: 0.75 }} />
                </div>
                <p style={{
                  fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                  letterSpacing: '0.14em', textTransform: 'uppercase',
                  color: '#c9a96e', marginBottom: 10,
                }}>{step.n}</p>
                <h3 style={{
                  fontFamily: "'Playfair Display', serif",
                  fontSize: 22, fontWeight: 700, color: '#f0ece4', marginBottom: 10,
                }}>{step.title}</h3>
                <p style={{
                  fontFamily: 'DM Sans, sans-serif', fontSize: 14, lineHeight: 1.65,
                  color: 'rgba(240,236,228,0.45)',
                }}>{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FEATURE LIST — cream ────────────────────────────────────── */}
      <section style={{ background: '#f0ece4', padding: '100px 60px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 80, alignItems: 'center' }}>
          <div>
            <img
              src="https://images.unsplash.com/photo-1662532577856-e8ee8b138a8b?w=700&h=860&fit=crop&auto=format"
              alt="editorial fashion"
              style={{ width: '100%', borderRadius: 8, display: 'block', objectFit: 'cover' }}
              className="img-zoom"
            />
          </div>
          <div>
            <p style={{
              fontFamily: 'DM Sans, sans-serif', fontSize: 11,
              letterSpacing: '0.16em', textTransform: 'uppercase',
              color: '#a09080', marginBottom: 20,
            }}>Why Cobaju</p>
            <h2 style={{
              fontFamily: "'Playfair Display', serif",
              fontSize: 'clamp(34px, 4vw, 52px)',
              fontWeight: 700, lineHeight: 1.08,
              color: '#1a1816', marginBottom: 48,
            }}>
              Style that starts<br />
              <em style={{ fontStyle: 'italic' }}>with you.</em>
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
              {features.map((f, i) => (
                <div key={i} style={{ display: 'flex', gap: 20 }}>
                  <div style={{
                    flexShrink: 0, width: 2, background: '#c9a96e',
                    borderRadius: 999, alignSelf: 'stretch', minHeight: 40,
                  }} />
                  <div>
                    <div style={{
                      fontFamily: "'Playfair Display', serif",
                      fontSize: 18, fontWeight: 700, color: '#1a1816', marginBottom: 6,
                    }}>{f.label}</div>
                    <div style={{
                      fontFamily: 'DM Sans, sans-serif', fontSize: 14,
                      lineHeight: 1.65, color: '#6b6055',
                    }}>{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
            <button onClick={() => onNavigate('stylist')} style={{
              marginTop: 48,
              fontFamily: 'DM Sans, sans-serif', fontSize: 13,
              fontWeight: 600, background: '#1a1816',
              color: '#f7f4ef', border: 'none', borderRadius: 999,
              padding: '14px 32px', cursor: 'pointer',
            }}>
              Try the AI Stylist →
            </button>
          </div>
        </div>
      </section>

      {/* ── QUOTE ───────────────────────────────────────────────────── */}
      <section style={{ background: '#100f0d', padding: '120px 60px', textAlign: 'center' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.3)', marginBottom: 32,
        }}>From the wardrobe</p>
        <blockquote style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 'clamp(28px, 4vw, 52px)',
          fontStyle: 'italic',
          fontWeight: 400, lineHeight: 1.25,
          color: '#f0ece4',
          maxWidth: 800, margin: '0 auto 28px',
        }}>
          "The most sustainable wardrobe is the one you already have."
        </blockquote>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 13,
          color: 'rgba(255,255,255,0.35)', letterSpacing: '0.06em',
        }}>— Cobaju, 2025</p>
        <button onClick={() => onNavigate('wardrobe')} style={{
          marginTop: 48,
          fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 600,
          background: '#c9a96e', color: '#100f0d',
          border: 'none', borderRadius: 999, padding: '14px 36px', cursor: 'pointer',
        }}>
          Open my wardrobe
        </button>
      </section>
    </div>
  )
}
