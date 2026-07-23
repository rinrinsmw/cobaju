import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, fetchItemImage, getToken } from '../api'
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

function LookbookItemPhoto({ item }: { item: HistoricalItem }) {
  const image = useQuery({
    queryKey: ['item-image', item.item_id],
    queryFn: () => fetchItemImage(item.item_id),
    enabled: item.available,
    staleTime: Infinity,
    retry: false,
  })
  const [imageUrl, setImageUrl] = useState('')
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageFailed, setImageFailed] = useState(false)
  const [showFullImage, setShowFullImage] = useState(false)

  useEffect(() => {
    setImageLoaded(false)
    setImageFailed(false)
    setShowFullImage(false)
    if (!image.data) {
      setImageUrl('')
      return
    }

    const objectUrl = URL.createObjectURL(image.data)
    setImageUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [image.data, item.item_id])

  const showImage = Boolean(imageUrl) && !imageFailed
  const showSkeleton = item.available && !imageFailed && (image.isPending || (showImage && !imageLoaded))
  const fallback = item.available ? categoryEmoji[item.category ?? ''] || '✦' : '◌'

  return (
    <div
      onMouseEnter={() => setShowFullImage(true)}
      onMouseLeave={() => setShowFullImage(false)}
      title={showImage ? 'Hover to view the full image' : undefined}
      style={{
        position: 'relative', minWidth: 0, minHeight: 0,
        overflow: 'hidden', borderRadius: 8, background: 'rgba(247,244,239,.72)',
      }}
    >
      {showImage && (
        <img
          src={imageUrl}
          alt={item.name ?? `${item.category ?? 'wardrobe'} item`}
          onLoad={() => setImageLoaded(true)}
          onError={() => setImageFailed(true)}
          style={{
            width: '100%', height: '100%', display: 'block',
            objectFit: showFullImage ? 'contain' : 'cover',
            opacity: imageLoaded ? 1 : 0,
            background: showFullImage ? '#fff' : 'transparent',
            transition: 'background-color .2s ease',
          }}
        />
      )}
      {showSkeleton && (
        <span
          className="wardrobe-image-skeleton"
          aria-label={`Loading ${item.name ?? item.category ?? 'wardrobe item'} image`}
        />
      )}
      {!showImage && !showSkeleton && (
        <span
          aria-label={`${item.name ?? item.category ?? 'Wardrobe item'} image unavailable`}
          style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', fontSize: 44 }}
        >
          {fallback}
        </span>
      )}
    </div>
  )
}

function displayDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

export default function History({ onNavigate }: Props) {
  const queryClient = useQueryClient()
  const isAuthenticated = Boolean(getToken())
  const [pendingDelete, setPendingDelete] = useState<RecommendationHistory | null>(null)
  const [toast, setToast] = useState('')
  const history = useQuery({
    queryKey: ['history'],
    queryFn: () => apiRequest<RecommendationHistory[]>('/recommendations'),
    enabled: isAuthenticated,
  })
  const looks = history.data ?? []
  const loading = isAuthenticated && history.isPending
  const message = !isAuthenticated
    ? 'Log in to see your saved recommendations.'
    : history.error instanceof Error ? history.error.message : ''
  const deletion = useMutation({
    mutationFn: (recommendationId: number) => apiRequest<void>(`/recommendations/${recommendationId}`, { method: 'DELETE' }),
    onSuccess: (_, recommendationId) => {
      queryClient.setQueryData<RecommendationHistory[]>(['history'], current => current?.filter(look => look.id !== recommendationId) ?? [])
      queryClient.invalidateQueries({ queryKey: ['history'] })
      setPendingDelete(null)
      setToast('Look deleted from your Lookbook.')
    },
  })

  const confirmDelete = () => {
    if (pendingDelete && !deletion.isPending) deletion.mutate(pendingDelete.id)
  }

  return (
    <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
      <div style={{ background: '#f0ece4', padding: '72px 60px 56px', borderBottom: '1px solid rgba(0,0,0,0.06)' }}>
        <p style={{
          fontFamily: 'DM Sans, sans-serif', fontSize: 11,
          letterSpacing: '0.16em', textTransform: 'uppercase',
          color: '#a09080', marginBottom: 16,
        }}>Lookbook</p>
        <div>
          <h1 style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 'clamp(36px, 5vw, 64px)',
            fontWeight: 700, lineHeight: 1.05, color: '#1a1816',
          }}>
            {loading ? 'Your outfits,' : `${looks.length} outfit${looks.length === 1 ? '' : 's'},`}<br />
            <em style={{ fontStyle: 'italic', color: '#c9a96e' }}>your history.</em>
          </h1>
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
                  <div style={{
                    position: 'absolute', inset: 14, bottom: 62,
                    display: 'grid',
                    gridTemplateColumns: `repeat(${Math.min(2, Math.max(1, look.items.length))}, minmax(0, 1fr))`,
                    gridAutoRows: 'minmax(0, 1fr)', gap: 8,
                  }}>
                    {look.items.length > 0
                      ? look.items.map(item => <LookbookItemPhoto key={item.item_id} item={item} />)
                      : <span style={{ display: 'grid', placeItems: 'center', fontSize: 44 }}>✦</span>}
                  </div>
                  <button onClick={() => onNavigate('stylist', look.original_request)} style={{
                    position: 'absolute', left: 18, bottom: 18,
                    fontFamily: 'DM Sans, sans-serif', fontSize: 12, fontWeight: 600,
                    letterSpacing: '0.05em', textTransform: 'uppercase',
                    background: '#f0ece4', color: '#1a1816', border: 'none',
                    borderRadius: 999, padding: '8px 18px', cursor: 'pointer',
                  }}>Wear again</button>
                  <button aria-label={`Delete ${look.original_request}`} onClick={() => { deletion.reset(); setToast(''); setPendingDelete(look) }} style={{
                    position: 'absolute', right: 18, bottom: 18,
                    fontFamily: 'DM Sans, sans-serif', fontSize: 11, fontWeight: 600,
                    letterSpacing: '0.04em', textTransform: 'uppercase',
                    background: 'rgba(247,244,239,.88)', color: '#8b3832',
                    border: '1px solid rgba(139,56,50,.28)',
                    borderRadius: 999, padding: '7px 14px', cursor: 'pointer',
                  }}>Delete</button>
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
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {toast && <div role="status" style={{ position: 'fixed', right: 24, bottom: 24, zIndex: 210, background: '#1a1816', color: '#f7f4ef', borderRadius: 6, padding: '12px 18px', fontFamily: 'DM Sans, sans-serif', fontSize: 13 }}>{toast}</div>}
      {pendingDelete && <div role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !deletion.isPending) setPendingDelete(null) }} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(16,15,13,.62)', display: 'grid', placeItems: 'center', padding: 24 }}>
        <div role="dialog" aria-modal="true" aria-labelledby="delete-look-title" aria-describedby="delete-look-description" style={{ width: 'min(420px, 100%)', background: '#f7f4ef', borderRadius: 8, padding: 28, boxShadow: '0 24px 70px rgba(0,0,0,.24)' }}>
          <h2 id="delete-look-title" style={{ fontFamily: "'Playfair Display', serif", fontSize: 25, marginBottom: 10 }}>Delete this saved look?</h2>
          <p id="delete-look-description" style={{ color: '#6b6055', fontSize: 14, lineHeight: 1.5, marginBottom: 8 }}>This permanently removes the Lookbook entry. Your wardrobe items and clothing images will stay untouched.</p>
          {deletion.error && <p role="alert" style={{ color: '#8b3832', fontSize: 13, marginBottom: 8 }}>{deletion.error.message}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
            <button onClick={() => setPendingDelete(null)} disabled={deletion.isPending} style={{ padding: '9px 16px', borderRadius: 999, border: '1px solid rgba(0,0,0,.16)', background: 'transparent', color: '#1a1816', cursor: 'pointer' }}>Cancel</button>
            <button onClick={confirmDelete} disabled={deletion.isPending} style={{ padding: '9px 16px', borderRadius: 999, border: 0, background: '#8b3832', color: '#fff', cursor: 'pointer' }}>{deletion.isPending ? 'Deleting…' : 'Delete Look'}</button>
          </div>
        </div>
      </div>}
    </div>
  )
}
