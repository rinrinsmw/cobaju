import { useState, useEffect, useRef } from 'react'

interface Props { prefill?: string }

interface Msg {
  role: 'user' | 'ai'
  text?: string
  outfit?: { items: { emoji: string; label: string }[]; score: number; reasons: string[] }
}

const INIT: Msg = {
  role: 'ai',
  text: "Hi Alex — tell me where you're going or what you need to wear. I'll build an outfit from your wardrobe.",
}

const OUTFIT: Msg = {
  role: 'ai',
  outfit: {
    items: [
      { emoji: '👔', label: 'White Oxford' },
      { emoji: '👖', label: 'Black Trousers' },
      { emoji: '👞', label: 'Black Loafers' },
    ],
    score: 9.4,
    reasons: [
      'Professional and occasion-appropriate',
      'Neutral palette creates visual harmony',
      'All three items exist in your wardrobe',
    ],
  },
}

const quickPrompts = ['Interview outfit', 'Casual Friday', 'First date', 'Gallery opening', 'Weekend brunch']

export default function Stylist({ prefill = '' }: Props) {
  const [msgs, setMsgs] = useState<Msg[]>([INIT])
  const [input, setInput] = useState(prefill)
  const [thinking, setThinking] = useState(false)
  const [showDev, setShowDev] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (prefill) setTimeout(() => send(prefill), 400)
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [msgs, thinking])

  const send = (text?: string) => {
    const m = (text ?? input).trim()
    if (!m) return
    setInput('')
    setMsgs(p => [...p, { role: 'user', text: m }])
    setThinking(true)
    setTimeout(() => { setThinking(false); setMsgs(p => [...p, OUTFIT]) }, 1500)
  }

  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
      {/* Header */}
      <div style={{ background: '#100f0d', padding: '72px 60px 56px' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.35)', marginBottom: 16,
        }}>AI Stylist</p>
        <h1 style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 'clamp(36px, 5vw, 64px)',
          fontWeight: 700, lineHeight: 1.05,
          color: '#f0ece4',
        }}>
          What are you<br />
          <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>dressing for?</em>
        </h1>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 60px', display: 'grid', gridTemplateColumns: '1fr 360px', gap: 40 }}>
        {/* Chat panel */}
        <div style={{
          background: 'white', borderRadius: 8,
          border: '1px solid rgba(0,0,0,0.08)',
          display: 'flex', flexDirection: 'column',
          minHeight: 560,
        }}>
          {/* Messages */}
          <div ref={logRef} style={{
            flex: 1, overflowY: 'auto',
            padding: '28px 28px 0',
            display: 'flex', flexDirection: 'column', gap: 18,
            maxHeight: 480,
          }}>
            {msgs.map((msg, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                {msg.role === 'ai' && (
                  <div style={{
                    width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
                    background: '#1a1816', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', fontSize: 12, color: '#c9a96e',
                    marginRight: 10, marginTop: 2,
                  }}>✦</div>
                )}
                <div style={{ maxWidth: '78%' }}>
                  {msg.text && (
                    <div style={{
                      padding: '12px 16px', borderRadius: 8,
                      background: msg.role === 'user' ? '#1a1816' : '#f7f4ef',
                      color: msg.role === 'user' ? '#f0ece4' : '#1a1816',
                      fontFamily: 'DM Sans, sans-serif', fontSize: 14, lineHeight: 1.6,
                      borderBottomRightRadius: msg.role === 'user' ? 2 : 8,
                      borderBottomLeftRadius: msg.role === 'ai' ? 2 : 8,
                    }}>{msg.text}</div>
                  )}

                  {msg.outfit && (
                    <div style={{ border: '1px solid rgba(0,0,0,0.1)', borderRadius: 8, overflow: 'hidden', marginTop: msg.text ? 8 : 0 }}>
                      {/* Outfit header */}
                      <div style={{
                        background: '#1a1816', padding: '14px 18px',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      }}>
                        <span style={{
                          fontFamily: 'DM Sans, sans-serif', fontSize: 12,
                          letterSpacing: '0.08em', textTransform: 'uppercase', color: '#f0ece4',
                        }}>Recommended outfit</span>
                        <span style={{
                          fontFamily: "'Playfair Display', serif",
                          fontSize: 18, color: '#c9a96e',
                        }}>{msg.outfit.score}</span>
                      </div>

                      <div style={{ padding: '18px' }}>
                        {/* Pieces */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
                          {msg.outfit.items.map((item, j) => (
                            <div key={j} style={{
                              background: '#f7f4ef', borderRadius: 6, padding: '14px 8px',
                              textAlign: 'center', border: '1px solid rgba(0,0,0,0.06)',
                            }}>
                              <div style={{ fontSize: 32, marginBottom: 4 }}>{item.emoji}</div>
                              <div style={{
                                fontFamily: 'DM Sans, sans-serif', fontSize: 11,
                                color: '#6b6055',
                              }}>{item.label}</div>
                            </div>
                          ))}
                        </div>

                        {/* Reasons */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 16 }}>
                          {msg.outfit.reasons.map((r, j) => (
                            <div key={j} style={{
                              display: 'flex', gap: 10, alignItems: 'flex-start',
                              fontFamily: 'DM Sans, sans-serif', fontSize: 13, color: '#1a1816',
                            }}>
                              <span style={{ color: '#c9a96e', flexShrink: 0, marginTop: 1 }}>–</span>
                              {r}
                            </div>
                          ))}
                        </div>

                        <div style={{ display: 'flex', gap: 8 }}>
                          <button style={{
                            flex: 1, padding: '10px', cursor: 'pointer',
                            fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                            letterSpacing: '0.04em', textTransform: 'uppercase',
                            background: 'transparent', color: '#1a1816',
                            border: '1px solid rgba(0,0,0,0.15)', borderRadius: 999,
                          }}>Another</button>
                          <button style={{
                            flex: 1, padding: '10px', cursor: 'pointer',
                            fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                            letterSpacing: '0.04em', textTransform: 'uppercase',
                            background: '#1a1816', color: '#f7f4ef',
                            border: 'none', borderRadius: 999,
                          }}>Save look</button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {thinking && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: '50%', background: '#1a1816',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, color: '#c9a96e', flexShrink: 0,
                }}>✦</div>
                <div style={{
                  background: '#f7f4ef', borderRadius: 8, borderBottomLeftRadius: 2,
                  padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 10,
                }}>
                  <span style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 13, color: '#a09080' }}>
                    Searching wardrobe
                  </span>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {[0, 1, 2].map(i => (
                      <div key={i} style={{
                        width: 5, height: 5, borderRadius: '50%', background: '#c9a96e',
                      }} className={`dot-${i + 1}`} />
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div style={{ padding: '16px 20px', borderTop: '1px solid rgba(0,0,0,0.07)' }}>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send()}
                placeholder="Describe the occasion or look…"
                style={{
                  flex: 1, padding: '11px 16px',
                  fontFamily: 'DM Sans, sans-serif', fontSize: 14, color: '#1a1816',
                  background: '#f7f4ef', border: '1px solid rgba(0,0,0,0.1)',
                  borderRadius: 999, outline: 'none',
                }}
              />
              <button onClick={() => send()} disabled={thinking} style={{
                padding: '11px 22px',
                fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 600,
                background: '#1a1816', color: '#f7f4ef',
                border: 'none', borderRadius: 999, cursor: 'pointer',
                opacity: thinking ? 0.5 : 1,
              }}>Send</button>
            </div>
          </div>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Quick prompts */}
          <div style={{ background: 'white', borderRadius: 8, padding: '22px', border: '1px solid rgba(0,0,0,0.08)' }}>
            <p style={{
              fontFamily: 'DM Sans, sans-serif', fontSize: 11, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: '#a09080', marginBottom: 14,
            }}>Quick prompts</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {quickPrompts.map(p => (
                <button key={p} onClick={() => { setInput(p); send(p) }} style={{
                  fontFamily: 'DM Sans, sans-serif', fontSize: 13, color: '#1a1816',
                  background: 'transparent', border: 'none', cursor: 'pointer',
                  textAlign: 'left', padding: '9px 0',
                  borderBottom: '1px solid rgba(0,0,0,0.06)',
                  transition: 'color 0.15s',
                }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#c9a96e')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#1a1816')}
                >
                  {p} →
                </button>
              ))}
            </div>
          </div>

          {/* Agent workflow */}
          <div style={{ background: 'white', borderRadius: 8, padding: '22px', border: '1px solid rgba(0,0,0,0.08)' }}>
            <p style={{
              fontFamily: 'DM Sans, sans-serif', fontSize: 11, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: '#a09080', marginBottom: 18,
            }}>How it works</p>
            {[
              { n: 1, title: 'Parse request', sub: 'Occasion + style context' },
              { n: 2, title: 'Search wardrobe', sub: 'Only what you own' },
              { n: 3, title: 'Build outfit', sub: 'Top · bottom · shoes' },
              { n: 4, title: 'Score result', sub: 'Evaluate fit and coherence' },
            ].map(s => (
              <div key={s.n} style={{
                display: 'flex', gap: 14, padding: '10px 0',
                borderBottom: '1px solid rgba(0,0,0,0.06)',
              }}>
                <span style={{
                  fontFamily: "'Playfair Display', serif",
                  fontSize: 12, color: '#c9a96e', flexShrink: 0, marginTop: 1,
                }}>0{s.n}</span>
                <div>
                  <div style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 13, fontWeight: 600, color: '#1a1816' }}>{s.title}</div>
                  <div style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 12, color: '#a09080' }}>{s.sub}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Dev mode toggle */}
          <button onClick={() => setShowDev(v => !v)} style={{
            fontFamily: 'DM Sans, sans-serif', fontSize: 11,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            color: showDev ? '#f7f4ef' : '#a09080',
            background: showDev ? '#1a1816' : 'transparent',
            border: '1px solid rgba(0,0,0,0.12)', borderRadius: 6,
            padding: '10px', cursor: 'pointer',
          }}>
            {showDev ? '✦ Developer mode on' : 'Developer mode'}
          </button>

          {showDev && (
            <div style={{ background: '#100f0d', borderRadius: 8, padding: '22px' }}>
              <p style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 11, letterSpacing: '0.1em',
                textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 14,
              }}>Metrics</p>
              {[
                { label: 'Retrieved items', value: '6' },
                { label: 'Latency', value: '2.8 s' },
                { label: 'Est. cost', value: '$0.004' },
                { label: 'Evaluator', value: 'PASS', gold: true },
              ].map(m => (
                <div key={m.label} style={{
                  display: 'flex', justifyContent: 'space-between',
                  padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.07)',
                  fontFamily: 'DM Sans, sans-serif', fontSize: 13,
                }}>
                  <span style={{ color: 'rgba(255,255,255,0.4)' }}>{m.label}</span>
                  <strong style={{ color: m.gold ? '#c9a96e' : '#f0ece4' }}>{m.value}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
