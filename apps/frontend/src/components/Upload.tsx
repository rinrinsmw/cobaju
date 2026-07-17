import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Page } from '../data'
import { apiRequest, type ClothingCategory, type ClothingItem, type ProcessingResult } from '../api'

interface Props { onNavigate: (page: Page) => void }
type Stage = 'idle' | 'uploading' | 'analyzing' | 'done' | 'error'
const categories: ClothingCategory[] = ['top', 'bottom', 'dress', 'outerwear', 'shoes', 'bag', 'accessory']
const delay = (milliseconds: number) => new Promise(resolve => window.setTimeout(resolve, milliseconds))

export default function Upload({ onNavigate }: Props) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [dragging, setDragging] = useState(false)
  const [preview, setPreview] = useState('')
  const [item, setItem] = useState<ClothingItem | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const runAnalysis = async (draft: ClothingItem) => {
    setError(''); setStage('analyzing')
    try {
      await apiRequest(`/wardrobe/items/${draft.id}/analyze`, { method: 'POST' })
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await delay(1000)
        const status = await apiRequest<ProcessingResult>(`/wardrobe/items/${draft.id}/status`)
        if (status.needs_confirmation) {
          setItem(await apiRequest<ClothingItem>(`/wardrobe/items/${draft.id}`))
          setStage('done')
          return
        }
        if (status.status === 'failed') throw new Error('Cobaju could not identify one clear clothing item in this image.')
      }
      throw new Error('Analysis is taking longer than expected. You can retry from this page.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Analysis failed.')
      setStage('error')
    }
  }

  const upload = async (file: File) => {
    if (preview) URL.revokeObjectURL(preview)
    setPreview(URL.createObjectURL(file)); setError(''); setStage('uploading')
    const form = new FormData(); form.append('image', file)
    try {
      const draft = await apiRequest<ClothingItem>('/wardrobe/items/upload', { method: 'POST', body: form })
      setItem(draft)
      await runAnalysis(draft)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed.')
      setStage('error')
    }
  }

  const choose = (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; if (file) void upload(file) }
  const drop = (event: DragEvent) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) void upload(file) }
  const change = (field: keyof ClothingItem, value: string) => setItem(current => current ? { ...current, [field]: value } : current)

  const save = async () => {
    if (!item) return
    setSaving(true); setError('')
    try {
      await apiRequest(`/wardrobe/items/${item.id}`, { method: 'PATCH', body: JSON.stringify({ name: item.name, category: item.category, color: item.color, description: item.description }) })
      await apiRequest(`/wardrobe/items/${item.id}/confirm`, { method: 'POST' })
      await queryClient.invalidateQueries({ queryKey: ['wardrobe'] })
      onNavigate('wardrobe')
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Could not save this piece.') }
    finally { setSaving(false) }
  }

  return <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
    <div className="page-header" style={{ background: '#f0ece4', padding: '72px 60px 56px', borderBottom: '1px solid rgba(0,0,0,.06)' }}>
      <p style={eyebrow}>New piece</p><h1 style={title}>Add to your<br /><em style={{ color: '#c9a96e' }}>collection.</em></h1>
    </div>
    <div className="two-column page-content" style={{ maxWidth: 1100, margin: '0 auto', padding: '64px 60px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 60 }}>
      <div>
        <input ref={inputRef} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={choose} />
        {stage === 'idle' ? <button onClick={() => inputRef.current?.click()} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={drop} style={{ ...dropzone, borderColor: dragging ? '#1a1816' : 'rgba(0,0,0,.2)' }}>
          <span style={{ fontSize: 40, color: '#a09080' }}>▧</span><span style={{ fontFamily: "'Playfair Display', serif", fontSize: 20 }}>Drop your photo here</span><span style={{ color: '#a09080', fontSize: 13 }}>JPG, PNG or WebP · One item · Max 5 MB</span><span style={darkPill}>Choose file</span>
        </button> : <div style={{ height: 460, borderRadius: 8, overflow: 'hidden', background: '#e8e0d4', position: 'relative' }}>
          <img src={preview} alt="Selected clothing" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: stage === 'done' || stage === 'error' ? 1 : .45 }} />
          {(stage === 'uploading' || stage === 'analyzing') && <div style={overlay}><div className="spinner" /><span>{stage === 'uploading' ? 'Creating your piece…' : 'Analysing with AI…'}</span></div>}
        </div>}
      </div>
      <div>
        {stage === 'idle' && <Intro />}
        {(stage === 'uploading' || stage === 'analyzing') && <Processing stage={stage} />}
        {stage === 'error' && <div><h2 style={sectionTitle}>Something needs attention</h2><p role="alert" style={{ color: '#9f3a32', lineHeight: 1.6, marginBottom: 24 }}>{error}</p>{item && <button onClick={() => void runAnalysis(item)} style={darkButton}>Retry analysis</button>}<button onClick={() => { setStage('idle'); setItem(null); setError('') }} style={secondaryButton}>Choose another image</button></div>}
        {stage === 'done' && item && <div><h2 style={sectionTitle}>Analysis complete</h2><div style={{ display: 'grid', gap: 14 }}>
          <Field label="Name"><input value={item.name} onChange={event => change('name', event.target.value)} style={fieldStyle} /></Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}><Field label="Category"><select value={item.category} onChange={event => change('category', event.target.value)} style={fieldStyle}>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select></Field><Field label="Colour"><input value={item.color} onChange={event => change('color', event.target.value)} style={fieldStyle} /></Field></div>
          <Field label="Description"><textarea value={item.description ?? ''} onChange={event => change('description', event.target.value)} rows={4} style={fieldStyle} /></Field>
          {error && <p role="alert" style={{ color: '#9f3a32', fontSize: 13 }}>{error}</p>}
          <button disabled={saving} onClick={() => void save()} style={darkButton}>{saving ? 'Saving…' : 'Save to wardrobe'}</button>
        </div></div>}
      </div>
    </div>
  </div>
}

function Intro() { return <><h2 style={sectionTitle}>AI will handle the rest</h2><p style={{ color: '#6b6055', lineHeight: 1.7, marginBottom: 38 }}>Upload a clear photo of one clothing item. Cobaju identifies its category, colour, and description for your review.</p>{['Upload one clear item', 'Analyse visible details', 'Review and save'].map((text, index) => <div key={text} style={{ display: 'flex', gap: 18, padding: '13px 0', borderBottom: '1px solid rgba(0,0,0,.07)' }}><span style={{ color: '#c9a96e' }}>0{index + 1}</span>{text}</div>)}</> }
function Processing({ stage }: { stage: Stage }) { return <><h2 style={sectionTitle}>Processing…</h2>{['Image and record created', 'Clothing guardrail', 'Metadata analysis'].map((text, index) => <div key={text} style={{ padding: '14px 0', borderBottom: '1px solid rgba(0,0,0,.07)', color: index === 0 || stage === 'analyzing' ? '#1a1816' : '#a09080' }}>{index === 0 ? '✓ ' : '○ '}{text}</div>)}</> }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: '#a09080' }}>{label}{children}</label> }

const eyebrow = { fontSize: 11, letterSpacing: '.16em', textTransform: 'uppercase' as const, color: '#a09080', marginBottom: 16 }
const title = { fontFamily: "'Playfair Display', serif", fontSize: 'clamp(36px, 4vw, 56px)', lineHeight: 1.05 }
const sectionTitle = { fontFamily: "'Playfair Display', serif", fontSize: 28, marginBottom: 24 }
const dropzone = { width: '100%', height: 460, border: '1.5px dashed', borderRadius: 8, background: 'transparent', display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 18, cursor: 'pointer' }
const overlay = { position: 'absolute' as const, inset: 0, display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 14, background: 'rgba(247,244,239,.72)' }
const fieldStyle = { display: 'block', width: '100%', marginTop: 7, padding: '11px 12px', border: '1px solid rgba(0,0,0,.13)', borderRadius: 6, background: 'white', font: 'inherit', color: '#1a1816' }
const darkButton = { width: '100%', padding: 13, border: 0, borderRadius: 6, background: '#1a1816', color: '#f7f4ef', cursor: 'pointer', fontWeight: 600 }
const secondaryButton = { ...darkButton, marginTop: 10, background: 'transparent', color: '#1a1816', border: '1px solid rgba(0,0,0,.14)' }
const darkPill = { padding: '10px 22px', borderRadius: 999, background: '#1a1816', color: '#f7f4ef', fontSize: 12 }
