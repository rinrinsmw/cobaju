import { useState } from 'react'
import type { Page } from '../data'

interface Props { onNavigate: (p: Page) => void }
type Stage = 'idle' | 'uploading' | 'analyzing' | 'done'

export default function Upload({ onNavigate }: Props) {
  const [stage, setStage] = useState<Stage>('idle')
  const [dragging, setDragging] = useState(false)
  const [saved, setSaved] = useState(false)

  const simulate = () => {
    setStage('uploading')
    setTimeout(() => setStage('analyzing'), 1000)
    setTimeout(() => setStage('done'), 2400)
  }

  const handleSave = () => {
    setSaved(true)
    setTimeout(() => onNavigate('wardrobe'), 1200)
  }

  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ background: '#f0ece4', padding: '72px 60px 56px', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: '#a09080', marginBottom: 16,
        }}>New piece</p>
        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 'clamp(36px, 4vw, 56px)',
          fontWeight: 700, lineHeight: 1.05, color: '#1a1816',
        }}>
          Add to your<br />
          <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>collection.</em>
        </h1>
      </div>

      {/* Body */}
      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '64px 60px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60 }}>
        {/* Left: drop zone or preview */}
        <div>
          {stage === 'idle' ? (
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); simulate() }}
              onClick={simulate}
              style={{
                height: 460,
                border: dragging ? '1.5px solid #1a1816' : '1.5px dashed rgba(0,0,0,0.2)',
                borderRadius: 8,
                background: dragging ? 'rgba(26,24,22,0.03)' : 'transparent',
                display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                gap: 20, cursor: 'pointer',
                transition: 'border-color 0.2s, background 0.2s',
              }}
            >
              <svg width={40} height={40} viewBox="0 0 24 24" fill="none" stroke="rgba(0,0,0,0.25)" strokeWidth={1.2}>
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M3 15l5-5 4 4 3-3 6 6" />
                <circle cx="8.5" cy="8.5" r="1.5" />
              </svg>
              <div style={{ textAlign: 'center' }}>
                <p style={{
                  fontFamily: "'Playfair Display', serif",
                  fontSize: 20, color: '#1a1816', marginBottom: 8,
                }}>Drop your photo here</p>
                <p style={{
                  fontFamily: 'DM Sans, sans-serif', fontSize: 13,
                  color: '#a09080', lineHeight: 1.6,
                }}>JPG, PNG or WebP · One item per photo<br />Max 5 MB</p>
              </div>
              <button style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                letterSpacing: '0.06em', textTransform: 'uppercase',
                background: '#1a1816', color: '#f7f4ef',
                border: 'none', borderRadius: 999, padding: '10px 24px', cursor: 'pointer',
              }}>
                Choose file
              </button>
            </div>
          ) : (
            <div style={{
              height: 460, borderRadius: 8, overflow: 'hidden',
              background: '#e8e0d4', position: 'relative',
            }}>
              <img
                src="https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=600&h=600&fit=crop&auto=format"
                alt="uploaded shirt"
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: stage === 'done' ? 1 : 0.5, transition: 'opacity 0.5s' }}
              />
              {stage !== 'done' && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center', gap: 14,
                  background: 'rgba(247,244,239,0.7)', backdropFilter: 'blur(4px)',
                }}>
                  {/* Spinner */}
                  <div style={{
                    width: 36, height: 36,
                    border: '2px solid rgba(26,24,22,0.12)',
                    borderTop: '2px solid #1a1816',
                    borderRadius: '50%',
                    animation: 'spin 0.7s linear infinite',
                  }} />
                  <p style={{
                    fontFamily: 'DM Sans, sans-serif', fontSize: 13, color: '#1a1816',
                  }}>
                    {stage === 'uploading' ? 'Uploading…' : 'Analysing with AI…'}
                  </p>
                </div>
              )}
              {stage === 'done' && (
                <div style={{
                  position: 'absolute', top: 14, left: 14,
                  fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  background: '#f0ece4', color: '#1a1816',
                  padding: '6px 12px', borderRadius: 999,
                }}>
                  ✓ Background removed
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: analysis */}
        <div>
          {stage === 'idle' && (
            <>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 28, fontWeight: 700, color: '#1a1816', marginBottom: 12,
              }}>AI will handle the rest</h2>
              <p style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 14, lineHeight: 1.7,
                color: '#6b6055', marginBottom: 44,
              }}>
                Upload a clear photo of one clothing item. Cobaju identifies category, primary colour, style, and occasion — then adds it to your wardrobe instantly.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                {[
                  { n: '01', title: 'Upload', desc: 'One item, clear background preferred.' },
                  { n: '02', title: 'Analyse', desc: 'Category, colour, and occasion tagged automatically.' },
                  { n: '03', title: 'Save', desc: 'Review any field and confirm.' },
                ].map(s => (
                  <div key={s.n} style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
                    <span style={{
                      fontFamily: "'Playfair Display', serif",
                      fontSize: 13, color: '#c9a96e', flexShrink: 0, marginTop: 2,
                    }}>{s.n}</span>
                    <div>
                      <div style={{
                        fontFamily: 'DM Sans, sans-serif', fontSize: 14, fontWeight: 600,
                        color: '#1a1816', marginBottom: 3,
                      }}>{s.title}</div>
                      <div style={{
                        fontFamily: 'DM Sans, sans-serif', fontSize: 13,
                        color: '#a09080', lineHeight: 1.5,
                      }}>{s.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {(stage === 'uploading' || stage === 'analyzing') && (
            <div>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 28, fontWeight: 700, color: '#1a1816', marginBottom: 32,
              }}>Processing…</h2>
              {[
                { label: 'Image received', done: true },
                { label: 'Background removed', done: stage === 'analyzing' },
                { label: 'AI classification', done: false },
              ].map((s, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 14, alignItems: 'center',
                  padding: '14px 0', borderBottom: '1px solid rgba(0,0,0,0.07)',
                }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
                    background: s.done ? '#1a1816' : 'rgba(0,0,0,0.07)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: s.done ? '#f7f4ef' : 'transparent', fontSize: 12,
                  }}>
                    {s.done ? '✓' : ''}
                  </div>
                  <span style={{
                    fontFamily: 'DM Sans, sans-serif', fontSize: 14,
                    color: s.done ? '#1a1816' : '#a09080',
                  }}>{s.label}</span>
                </div>
              ))}
            </div>
          )}

          {stage === 'done' && (
            <div>
              <h2 style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 28, fontWeight: 700, color: '#1a1816', marginBottom: 28,
              }}>Analysis complete</h2>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                {[
                  { label: 'Category', value: 'Shirt', type: 'select', opts: ['Shirt', 'T-Shirt', 'Jacket', 'Trousers', 'Shoes'] },
                  { label: 'Colour', value: 'White', type: 'input' },
                  { label: 'Style', value: 'Smart casual', type: 'select', opts: ['Casual', 'Smart casual', 'Formal'] },
                  { label: 'Occasion', value: 'Office, dinner', type: 'input' },
                ].map(f => (
                  <div key={f.label}>
                    <label style={{
                      display: 'block', fontFamily: 'DM Sans, sans-serif',
                      fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
                      color: '#a09080', marginBottom: 6,
                    }}>{f.label}</label>
                    {f.type === 'select' ? (
                      <select defaultValue={f.value} style={{
                        width: '100%', padding: '10px 12px', fontFamily: 'DM Sans, sans-serif',
                        fontSize: 14, color: '#1a1816',
                        border: '1px solid rgba(0,0,0,0.12)', borderRadius: 6,
                        background: 'white', outline: 'none',
                      }}>
                        {f.opts?.map(o => <option key={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input defaultValue={f.value} style={{
                        width: '100%', padding: '10px 12px', fontFamily: 'DM Sans, sans-serif',
                        fontSize: 14, color: '#1a1816',
                        border: '1px solid rgba(0,0,0,0.12)', borderRadius: 6,
                        background: 'white', outline: 'none',
                      }} />
                    )}
                  </div>
                ))}
              </div>

              <div style={{ marginBottom: 28 }}>
                <label style={{
                  display: 'block', fontFamily: 'DM Sans, sans-serif',
                  fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
                  color: '#a09080', marginBottom: 6,
                }}>Description</label>
                <input defaultValue="White Oxford shirt, smart-casual. Good for office and dinner." style={{
                  width: '100%', padding: '10px 12px', fontFamily: 'DM Sans, sans-serif',
                  fontSize: 14, color: '#1a1816',
                  border: '1px solid rgba(0,0,0,0.12)', borderRadius: 6,
                  background: 'white', outline: 'none',
                }} />
              </div>

              <button onClick={handleSave} style={{
                width: '100%', padding: '14px',
                fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 600,
                letterSpacing: '0.04em', textTransform: 'uppercase',
                background: saved ? '#c9a96e' : '#1a1816',
                color: saved ? '#1a1816' : '#f7f4ef',
                border: 'none', borderRadius: 6, cursor: 'pointer',
                transition: 'background 0.3s, color 0.3s',
              }}>
                {saved ? '✓ Saved to wardrobe' : 'Save to wardrobe'}
              </button>
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
