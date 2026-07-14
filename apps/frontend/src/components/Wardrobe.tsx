import { useState } from 'react'
import type { Page } from '../data'
import { wardrobe as items } from '../data'

interface Props { onNavigate: (p: Page) => void }

const cats = ['All', 'Top', 'Bottom', 'Outerwear', 'Shoes']
const styles = ['All styles', 'Casual', 'Smart casual', 'Formal']

const styleTag: Record<string, { bg: string; color: string }> = {
  Casual:         { bg: 'rgba(0,0,0,0.06)', color: '#4a4035' },
  'Smart casual': { bg: 'rgba(0,0,0,0.06)', color: '#4a4035' },
  Formal:         { bg: 'rgba(0,0,0,0.06)', color: '#4a4035' },
}

export default function Wardrobe({ onNavigate }: Props) {
  const [search, setSearch] = useState('')
  const [cat, setCat] = useState('All')
  const [style, setStyle] = useState('All styles')
  const [saved, setSaved] = useState<Set<number>>(new Set([0, 3, 7]))
  const [hovered, setHovered] = useState<number | null>(null)

  const filtered = items.filter((item, i) => {
    const matchS = item.name.toLowerCase().includes(search.toLowerCase())
    const matchC = cat === 'All' || item.category === cat
    const matchSt = style === 'All styles' || item.style === style
    return matchS && matchC && matchSt
  })

  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
      {/* Page header */}
      <div style={{ background: '#1a1816', padding: '72px 60px 56px' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.35)', marginBottom: 16,
        }}>My wardrobe</p>
        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 'clamp(36px, 5vw, 64px)',
          fontWeight: 700, lineHeight: 1.05,
          color: '#f0ece4', marginBottom: 0,
        }}>
          {filtered.length} pieces,<br />
          <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>all yours.</em>
        </h1>
      </div>

      {/* Filters bar */}
      <div style={{
        position: 'sticky', top: 64, zIndex: 50,
        background: 'rgba(247,244,239,0.95)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid rgba(0,0,0,0.07)',
        padding: '14px 60px',
        display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap',
      }}>
        {/* Search */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search…"
          style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 13,
            padding: '8px 16px', borderRadius: 999,
            border: '1px solid rgba(0,0,0,0.12)', background: 'white',
            color: '#1a1816', outline: 'none', width: 180,
          }}
        />
        {/* Category pills */}
        {cats.map(c => (
          <button key={c} onClick={() => setCat(c)} style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 12,
            letterSpacing: '0.04em', textTransform: 'uppercase',
            padding: '7px 16px', borderRadius: 999, cursor: 'pointer',
            background: cat === c ? '#1a1816' : 'white',
            color: cat === c ? '#f7f4ef' : '#1a1816',
            border: '1px solid rgba(0,0,0,0.12)',
            fontWeight: cat === c ? 600 : 400,
            transition: 'all 0.15s',
          }}>
            {c}
          </button>
        ))}
        <select value={style} onChange={e => setStyle(e.target.value)} style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 12,
          padding: '8px 14px', borderRadius: 999,
          border: '1px solid rgba(0,0,0,0.12)', background: 'white',
          color: '#1a1816', outline: 'none', cursor: 'pointer',
        }}>
          {styles.map(s => <option key={s}>{s}</option>)}
        </select>

        <button onClick={() => onNavigate('upload')} style={{
          marginLeft: 'auto',
          fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
          letterSpacing: '0.04em', textTransform: 'uppercase',
          padding: '8px 20px', borderRadius: 999, cursor: 'pointer',
          background: '#1a1816', color: '#f7f4ef', border: 'none',
        }}>
          + Add piece
        </button>
      </div>

      {/* Masonry grid */}
      <div style={{ padding: '48px 60px' }}>
        <div className="masonry">
          {filtered.map((item, idx) => {
            const i = items.indexOf(item)
            const isHov = hovered === i
            const isSaved = saved.has(i)
            /* alternating heights via padding-bottom trick on image */
            const heights = [320, 260, 380, 300, 340, 280, 360, 290]
            const h = heights[i % heights.length]

            return (
              <div key={i} className="masonry-item">
                <div
                  style={{
                    borderRadius: 6,
                    overflow: 'hidden',
                    background: '#e8e0d4',
                    cursor: 'pointer',
                    transition: 'transform 0.25s cubic-bezier(.22,.68,0,1.2), box-shadow 0.25s',
                    transform: isHov ? 'translateY(-5px)' : 'none',
                    boxShadow: isHov ? '0 20px 50px rgba(0,0,0,0.18)' : '0 2px 8px rgba(0,0,0,0.06)',
                    position: 'relative',
                  }}
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                >
                  {/* Photo */}
                  <div className="img-zoom" style={{ height: h, overflow: 'hidden', background: '#d4ccc0' }}>
                    <img
                      src={item.img}
                      alt={item.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
                    />
                  </div>

                  {/* Hover overlay */}
                  <div style={{
                    position: 'absolute', inset: 0,
                    background: 'linear-gradient(to top, rgba(16,15,13,0.72) 0%, transparent 55%)',
                    opacity: isHov ? 1 : 0,
                    transition: 'opacity 0.25s',
                    display: 'flex', flexDirection: 'column',
                    justifyContent: 'flex-end', padding: 16,
                  }}>
                    <button
                      onClick={() => onNavigate('stylist')}
                      style={{
                        alignSelf: 'flex-start',
                        fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                        background: '#f0ece4', color: '#1a1816',
                        border: 'none', borderRadius: 999,
                        padding: '8px 18px', cursor: 'pointer',
                      }}>
                      Style it
                    </button>
                  </div>

                  {/* Save button */}
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      setSaved(prev => {
                        const n = new Set(prev)
                        n.has(i) ? n.delete(i) : n.add(i)
                        return n
                      })
                    }}
                    style={{
                      position: 'absolute', top: 12, right: 12,
                      width: 32, height: 32, borderRadius: '50%',
                      background: isSaved ? '#c9a96e' : 'rgba(255,255,255,0.88)',
                      color: isSaved ? '#fff' : '#1a1816',
                      border: 'none', cursor: 'pointer', fontSize: 14,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      transition: 'background 0.2s, transform 0.15s',
                      transform: isSaved ? 'scale(1.1)' : 'scale(1)',
                    }}>
                    {isSaved ? '♥' : '♡'}
                  </button>
                </div>

                {/* Caption */}
                <div style={{ padding: '10px 4px 0' }}>
                  <div style={{
                    fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 500,
                    color: '#1a1816',
                  }}>{item.name}</div>
                  <div style={{ display: 'flex', gap: 6, marginTop: 5, alignItems: 'center' }}>
                    <span style={{
                      fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                      letterSpacing: '0.06em', textTransform: 'uppercase',
                      color: '#a09080',
                    }}>{item.category}</span>
                    <span style={{ color: '#c9b49a', fontSize: 10 }}>·</span>
                    <span style={{
                      fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                      ...styleTag[item.style],
                      padding: '2px 8px', borderRadius: 999,
                    }}>{item.style}</span>
                  </div>
                </div>
              </div>
            )
          })}

          {/* Add new */}
          <div className="masonry-item">
            <button onClick={() => onNavigate('upload')} style={{
              width: '100%', height: 240,
              border: '1px dashed rgba(0,0,0,0.18)',
              borderRadius: 6, background: 'transparent', cursor: 'pointer',
              display: 'flex', flexDirection: 'column',
              alignItems: 'center', justifyContent: 'center', gap: 12,
              transition: 'border-color 0.2s',
            }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = '#1a1816')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(0,0,0,0.18)')}
            >
              <span style={{ fontSize: 28, color: '#c9b49a' }}>+</span>
              <span style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 12,
                letterSpacing: '0.06em', textTransform: 'uppercase', color: '#a09080',
              }}>Add piece</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
