import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Page } from '../data'
import { apiRequest, fetchItemImage, type ClothingItem } from '../api'

interface Props { onNavigate: (page: Page, prefill?: string) => void }
const categories = ['All', 'Top', 'Bottom', 'Dress', 'Outerwear', 'Shoes', 'Bag', 'Accessory']
const emoji: Record<string, string> = { top: '👔', bottom: '👖', dress: '👗', outerwear: '🧥', shoes: '👞', bag: '👜', accessory: '⌚' }

function ItemPhoto({ item }: { item: ClothingItem }) {
  const { data } = useQuery({ queryKey: ['item-image', item.id], queryFn: () => fetchItemImage(item.id), enabled: Boolean(item.original_image_path), staleTime: Infinity })
  useEffect(() => () => { if (data) URL.revokeObjectURL(data) }, [data])
  return data
    ? <img src={data} alt={item.name} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
    : <div style={{ height: '100%', display: 'grid', placeItems: 'center', fontSize: 48 }}>{emoji[item.category] ?? '✦'}</div>
}

export default function Wardrobe({ onNavigate }: Props) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('All')
  const [hovered, setHovered] = useState<number | null>(null)
  const itemsQuery = useQuery({ queryKey: ['wardrobe'], queryFn: () => apiRequest<ClothingItem[]>('/wardrobe/items') })
  const remove = useMutation({
    mutationFn: (itemId: number) => apiRequest(`/wardrobe/items/${itemId}`, { method: 'DELETE' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['wardrobe'] }),
  })
  const filtered = (itemsQuery.data ?? []).filter(item =>
    item.name.toLowerCase().includes(search.toLowerCase()) &&
    (category === 'All' || item.category === category.toLowerCase()),
  )

  return <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
    <div className="page-header" style={{ background: '#1a1816', padding: '72px 60px 56px' }}>
      <p style={{ fontSize: 11, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,255,255,.35)', marginBottom: 16 }}>My wardrobe</p>
      <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 'clamp(36px, 5vw, 64px)', lineHeight: 1.05, color: '#f0ece4' }}>
        {itemsQuery.isPending ? 'Your pieces,' : `${filtered.length} piece${filtered.length === 1 ? '' : 's'},`}<br /><em style={{ color: '#c9a96e' }}>all yours.</em>
      </h1>
    </div>

    <div className="filter-bar" style={{ position: 'sticky', top: 64, zIndex: 50, background: 'rgba(247,244,239,.95)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(0,0,0,.07)', padding: '14px 60px', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search…" style={filterControl} />
      {categories.map(value => <button key={value} onClick={() => setCategory(value)} style={{ ...pill, background: category === value ? '#1a1816' : 'white', color: category === value ? '#f7f4ef' : '#1a1816' }}>{value}</button>)}
      <button onClick={() => onNavigate('upload')} style={{ ...pill, marginLeft: 'auto', background: '#1a1816', color: '#f7f4ef' }}>+ Add piece</button>
    </div>

    <div className="page-content" style={{ padding: '48px 60px' }}>
      {(itemsQuery.isPending || itemsQuery.error || (!filtered.length && !search && category === 'All')) && <EmptyState text={itemsQuery.isPending ? 'Loading your wardrobe…' : itemsQuery.error instanceof Error ? itemsQuery.error.message : 'Your wardrobe is ready for its first piece.'} action={!itemsQuery.isPending && !itemsQuery.error ? () => onNavigate('upload') : undefined} />}
      {!itemsQuery.isPending && !itemsQuery.error && filtered.length === 0 && (search || category !== 'All') && <EmptyState text="No pieces match these filters." />}
      <div className="masonry">
        {filtered.map((item, index) => <div key={item.id} className="masonry-item">
          <div onMouseEnter={() => setHovered(item.id)} onMouseLeave={() => setHovered(null)} style={{ height: [320, 260, 380, 300][index % 4], borderRadius: 6, overflow: 'hidden', background: '#ddd4c7', position: 'relative', transform: hovered === item.id ? 'translateY(-5px)' : 'none', transition: 'transform .25s' }}>
            <ItemPhoto item={item} />
            <div style={{ position: 'absolute', inset: 0, padding: 15, display: 'flex', alignItems: 'flex-end', gap: 8, background: 'linear-gradient(to top, rgba(16,15,13,.72), transparent 55%)', opacity: hovered === item.id ? 1 : 0, transition: 'opacity .2s' }}>
              <button onClick={() => onNavigate('stylist', `Style my ${item.name}`)} style={lightButton}>Style it</button>
              <button onClick={() => { if (window.confirm(`Delete ${item.name}?`)) remove.mutate(item.id) }} style={lightButton}>Delete</button>
            </div>
          </div>
          <div style={{ padding: '10px 4px 5px' }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{item.name}</div>
            <div style={{ fontSize: 11, color: '#a09080', textTransform: 'uppercase', marginTop: 5 }}>{item.category} · {item.color}</div>
            {item.processing_status !== 'completed' && <div style={{ fontSize: 11, color: item.processing_status === 'failed' ? '#9f3a32' : '#9a773d', marginTop: 4 }}>{item.processing_status === 'failed' ? 'Analysis failed' : 'Awaiting confirmation'}</div>}
          </div>
        </div>)}
      </div>
    </div>
  </div>
}

function EmptyState({ text, action }: { text: string; action?: () => void }) {
  return <div style={{ minHeight: 220, border: '1px dashed rgba(0,0,0,.18)', borderRadius: 6, display: 'grid', placeItems: 'center', textAlign: 'center', color: '#6b6055', marginBottom: 24 }}><div><div style={{ fontSize: 26, color: '#c9a96e', marginBottom: 10 }}>✦</div>{text}{action && <div><button onClick={action} style={{ ...pill, marginTop: 16, background: '#1a1816', color: '#f7f4ef' }}>Add your first piece</button></div>}</div></div>
}

const filterControl = { font: 'inherit', fontSize: 13, padding: '8px 16px', borderRadius: 999, border: '1px solid rgba(0,0,0,.12)', background: 'white', width: 180 }
const pill = { font: 'inherit', fontSize: 11, letterSpacing: '.04em', textTransform: 'uppercase' as const, padding: '8px 15px', borderRadius: 999, cursor: 'pointer', border: '1px solid rgba(0,0,0,.12)' }
const lightButton = { border: 0, borderRadius: 999, padding: '8px 15px', background: '#f0ece4', color: '#1a1816', cursor: 'pointer', fontSize: 12 }
