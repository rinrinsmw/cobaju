import type { Page } from '../data'

interface Props { onNavigate: (p: Page) => void }

const looks = [
  {
    title: 'Office Presentation',
    date: 'Today',
    occasion: 'Professional',
    score: 9.4,
    items: ['White Oxford', 'Black Trousers', 'Black Loafers'],
    img: 'https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&h=760&fit=crop&auto=format',
    h: 380,
  },
  {
    title: 'Casual Dinner',
    date: 'Yesterday',
    occasion: 'Smart Casual',
    score: 8.7,
    items: ['Black T-Shirt', 'Blue Jeans', 'White Sneakers'],
    img: 'https://images.unsplash.com/photo-1552374196-1ab2a1c593e8?w=600&h=640&fit=crop&auto=format',
    h: 320,
  },
  {
    title: 'Weekend Coffee',
    date: 'Last week',
    occasion: 'Casual',
    score: 8.2,
    items: ['Blue Polo', 'Khaki Chinos', 'White Sneakers'],
    img: 'https://images.unsplash.com/photo-1490114538077-0a7f8cb49891?w=600&h=700&fit=crop&auto=format',
    h: 350,
  },
  {
    title: 'Gallery Opening',
    date: '2 weeks ago',
    occasion: 'Formal',
    score: 9.6,
    items: ['Black Blazer', 'Black Trousers', 'Black Loafers'],
    img: 'https://images.unsplash.com/photo-1731589802397-6a1088d63630?w=600&h=720&fit=crop&auto=format',
    h: 360,
  },
  {
    title: 'First Date',
    date: '3 weeks ago',
    occasion: 'Smart Casual',
    score: 9.1,
    items: ['Black Blazer', 'Khaki Chinos', 'Brown Derby Shoes'],
    img: 'https://images.unsplash.com/photo-1578432156830-0ca0d7913b7f?w=600&h=680&fit=crop&auto=format',
    h: 340,
  },
  {
    title: 'Art Fair',
    date: 'Last month',
    occasion: 'Creative',
    score: 8.5,
    items: ['Beige Sweater', 'Blue Jeans', 'White Sneakers'],
    img: 'https://images.unsplash.com/photo-1662532577856-e8ee8b138a8b?w=600&h=660&fit=crop&auto=format',
    h: 330,
  },
]

export default function History({ onNavigate }: Props) {
  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ background: '#f0ece4', padding: '72px 60px 56px', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: '#a09080', marginBottom: 16,
        }}>Lookbook</p>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 'clamp(36px, 5vw, 64px)',
            fontWeight: 700, lineHeight: 1.05, color: '#1a1816',
          }}>
            {looks.length} outfits,<br />
            <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>your history.</em>
          </h1>
          <button onClick={() => onNavigate('stylist')} style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
            letterSpacing: '0.06em', textTransform: 'uppercase',
            background: '#1a1816', color: '#f7f4ef',
            border: 'none', borderRadius: 999, padding: '12px 28px', cursor: 'pointer',
            marginBottom: 6,
          }}>
            New look →
          </button>
        </div>
      </div>

      {/* Masonry lookbook */}
      <div style={{ padding: '48px 60px' }}>
        <div className="masonry">
          {looks.map((look, i) => (
            <div key={i} className="masonry-item" style={{ cursor: 'pointer' }}>
              <div
                className="img-zoom"
                style={{
                  borderRadius: 6, overflow: 'hidden',
                  background: '#d4ccc0', position: 'relative',
                  transition: 'box-shadow 0.25s',
                }}
                onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 16px 48px rgba(0,0,0,0.2)')}
                onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
              >
                <img
                  src={look.img}
                  alt={look.title}
                  style={{ width: '100%', height: look.h, objectFit: 'cover', display: 'block' }}
                />

                {/* Score badge */}
                <div style={{
                  position: 'absolute', top: 14, right: 14,
                  fontFamily: "'Playfair Display', serif",
                  fontSize: 14, color: '#1a1816',
                  background: '#f0ece4',
                  padding: '5px 11px', borderRadius: 999,
                }}>{look.score}</div>

                {/* Overlay on hover */}
                <div style={{
                  position: 'absolute', inset: 0,
                  background: 'linear-gradient(to top, rgba(16,15,13,0.75) 0%, transparent 50%)',
                  display: 'flex', flexDirection: 'column',
                  justifyContent: 'flex-end', padding: 18,
                  opacity: 0, transition: 'opacity 0.25s',
                }}
                  onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                  onMouseLeave={e => (e.currentTarget.style.opacity = '0')}
                >
                  <button onClick={() => onNavigate('stylist')} style={{
                    alignSelf: 'flex-start',
                    fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                    letterSpacing: '0.05em', textTransform: 'uppercase',
                    background: '#f0ece4', color: '#1a1816',
                    border: 'none', borderRadius: 999, padding: '8px 18px', cursor: 'pointer',
                  }}>Wear again</button>
                </div>
              </div>

              {/* Caption */}
              <div style={{ padding: '12px 2px 0' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{
                    fontFamily: "'Playfair Display', serif",
                    fontSize: 16, fontWeight: 700, color: '#1a1816',
                  }}>{look.title}</span>
                  <span style={{
                    fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                    color: '#a09080',
                  }}>{look.date}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {look.items.map((item, j) => (
                    <span key={j} style={{
                      fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                      color: '#6b6055',
                    }}>
                      {item}{j < look.items.length - 1 && <span style={{ color: '#c9b49a', marginLeft: 6 }}>·</span>}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}

          {/* CTA card */}
          <div className="masonry-item">
            <button onClick={() => onNavigate('stylist')} style={{
              width: '100%', height: 220,
              border: '1px dashed rgba(0,0,0,0.18)',
              borderRadius: 6, background: 'transparent', cursor: 'pointer',
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 12,
              transition: 'border-color 0.2s',
            }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#1a1816')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(0,0,0,0.18)')}
            >
              <span style={{ fontSize: 24, color: '#c9a96e' }}>✦</span>
              <span style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 12,
                letterSpacing: '0.08em', textTransform: 'uppercase', color: '#a09080',
              }}>Create new look</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
