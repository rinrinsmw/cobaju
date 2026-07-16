import { useEffect, useState } from 'react'
import type { Page } from '../data'

interface Props { onNavigate: (page: Page, prefill?: string) => void }

interface HistoricalItem {
  item_id: number
  available: boolean
  name: string | null
  category: string | null
  color: string | null
}

interface RecommendationHistory {
  id: number
  original_request: string
  selected_item_ids: number[]
  items: HistoricalItem[]
  explanation: string
  evaluation_score: number
  created_at: string
}

const categoryEmoji: Record<string, string> = {
  top: '👔', bottom: '👖', dress: '👗', outerwear: '🧥',
  shoes: '👞', bag: '👜', accessory: '⌚',
}

function displayDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

export default function History({ onNavigate }: Props) {
  const [looks, setLooks] = useState<RecommendationHistory[]>([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    const token = window.localStorage.getItem('access_token')
    if (!token) {
      setMessage('Log in to see your saved recommendations.')
      setLoading(false)
      return
    }

    const controller = new AbortController()
    fetch('/api/recommendations', {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401 ? 'Your session has expired. Please log in again.' : 'History could not be loaded.')
        return response.json() as Promise<RecommendationHistory[]>
      })
      .then(setLooks)
      .catch(error => {
        if (error instanceof Error && error.name !== 'AbortError') setMessage(error.message)
      })
      .finally(() => setLoading(false))

    return () => controller.abort()
  }, [])

  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
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
            {loading ? 'Your outfits,' : `${looks.length} outfit${looks.length === 1 ? '' : 's'},`}<br />
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

      <div style={{ padding: '48px 60px' }}>
        {(loading || message || looks.length === 0) && (
          <div style={{
            minHeight: 220, border: '1px dashed rgba(0,0,0,0.18)', borderRadius: 6,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
            fontFamily: 'DM Sans, sans-serif', color: '#6b6055', textAlign: 'center',
          }}>
            <span style={{ fontSize: 24, color: '#c9a96e' }}>✦</span>
            <span>{loading ? 'Loading your lookbook…' : message || 'No saved looks yet.'}</span>
            {!loading && !message && (
              <button onClick={() => onNavigate('stylist')} style={{
                fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                background: '#1a1816', color: '#f7f4ef', border: 'none',
                borderRadius: 999, padding: '10px 20px', cursor: 'pointer',
              }}>Create your first look</button>
            )}
          </div>
        )}

        {!loading && !message && looks.length > 0 && (
          <div className="masonry">
            {looks.map((look, index) => (
              <div key={look.id} className="masonry-item">
                <div style={{
                  height: 280 + (index % 3) * 35, borderRadius: 6, overflow: 'hidden',
                  background: 'linear-gradient(145deg, #ded5c8, #bcae9c)', position: 'relative',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <div style={{ display: 'flex', gap: 12, fontSize: 44, filter: 'drop-shadow(0 8px 12px rgba(0,0,0,0.12))' }}>
                    {look.items.length > 0
                      ? look.items.map(item => <span key={item.item_id}>{item.available ? categoryEmoji[item.category ?? ''] || '✦' : '◌'}</span>)
                      : <span>✦</span>}
                  </div>
                  <div style={{
                    position: 'absolute', top: 14, right: 14,
                    fontFamily: "'Playfair Display', serif", fontSize: 14, color: '#1a1816',
                    background: '#f0ece4', padding: '5px 11px', borderRadius: 999,
                  }}>{look.evaluation_score.toFixed(1)}</div>
                  <button onClick={() => onNavigate('stylist', look.original_request)} style={{
                    position: 'absolute', left: 18, bottom: 18,
                    fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                    letterSpacing: '0.05em', textTransform: 'uppercase',
                    background: '#f0ece4', color: '#1a1816', border: 'none',
                    borderRadius: 999, padding: '8px 18px', cursor: 'pointer',
                  }}>Wear again</button>
                </div>

                <div style={{ padding: '12px 2px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 16, marginBottom: 6 }}>
                    <span style={{
                      fontFamily: "'Playfair Display', serif", fontSize: 16,
                      fontWeight: 700, color: '#1a1816',
                    }}>{look.original_request}</span>
                    <span style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 11, color: '#a09080', flexShrink: 0 }}>
                      {displayDate(look.created_at)}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 7 }}>
                    {look.items.map((item, itemIndex) => (
                      <span key={item.item_id} style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 11, color: item.available ? '#6b6055' : '#a09080' }}>
                        {item.available ? item.name : `Deleted item #${item.item_id}`}
                        {itemIndex < look.items.length - 1 && <span style={{ color: '#c9b49a', marginLeft: 6 }}>·</span>}
                      </span>
                    ))}
                  </div>
                  <p style={{ fontFamily: 'DM Sans, sans-serif', fontSize: 12, lineHeight: 1.5, color: '#6b6055' }}>
                    {look.explanation}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
