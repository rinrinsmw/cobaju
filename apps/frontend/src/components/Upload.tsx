import { useEffect, useRef, useState, type ChangeEvent, type DragEvent, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Page } from '../data'
import { ApiError, apiRequest, type ClothingCategory, type ClothingItem, type ClothingUpload, type ProcessingResult } from '../api'

interface Props { onNavigate: (page: Page) => void }
type Stage = 'idle' | 'uploading' | 'analyzing' | 'done' | 'error'
type RecoveryAction = 'check-status' | 'retry-analysis' | 'none'
const categories: ClothingCategory[] = ['top', 'bottom', 'dress', 'outerwear', 'shoes', 'bag', 'accessory']
const delay = (milliseconds: number) => new Promise(resolve => window.setTimeout(resolve, milliseconds))
const supportedImageTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
const maximumImageBytes = 5 * 1024 * 1024

interface FieldErrors {
  name?: string
  color?: string
  description?: string
}

export default function Upload({ onNavigate }: Props) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [stage, setStage] = useState<Stage>('idle')
  const [dragging, setDragging] = useState(false)
  const [preview, setPreview] = useState('')
  const [item, setItem] = useState<ClothingItem | null>(null)
  const [analysisToken, setAnalysisToken] = useState('')
  const [error, setError] = useState('')
  const [recoveryAction, setRecoveryAction] = useState<RecoveryAction>('none')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])

  const pollAnalysis = async (draft: ClothingItem, pollingToken: string) => {
    setError(''); setRecoveryAction('none'); setStage('analyzing')
    try {
      for (let attempt = 0; attempt < 90; attempt += 1) {
        await delay(1000)
        const status = await apiRequest<ProcessingResult>(`/wardrobe/items/${draft.id}/status?analysis_token=${encodeURIComponent(pollingToken)}`)
        if (status.needs_confirmation) {
          setItem(await apiRequest<ClothingItem>(`/wardrobe/items/${draft.id}`))
          setStage('done')
          return
        }
        if (status.status === 'failed') {
          setError('Analysis failed. You can try the analysis again or choose another image.')
          setRecoveryAction('retry-analysis')
          setStage('error')
          return
        }
      }
      setError('Analysis is still processing, but status checks timed out while waiting.')
      setRecoveryAction('check-status')
      setStage('error')
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 422) {
        setItem(null)
        setRecoveryAction('none')
      } else {
        setRecoveryAction('check-status')
      }
      setError(
        caught instanceof ApiError && caught.status === 422
          ? caught.message
          : 'Could not check the analysis status. The item may still be processing.',
      )
      setStage('error')
    }
  }

  const runAnalysis = async (draft: ClothingItem, pollingToken: string) => {
    setError(''); setRecoveryAction('none'); setStage('analyzing')
    try {
      await apiRequest(`/wardrobe/items/${draft.id}/analyze`, { method: 'POST' })
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        await pollAnalysis(draft, pollingToken)
        return
      }
      setError(caught instanceof Error ? caught.message : 'Analysis could not be started.')
      setRecoveryAction('retry-analysis')
      setStage('error')
      return
    }
    await pollAnalysis(draft, pollingToken)
  }

  const validateFile = (file: File) => {
    if (!supportedImageTypes.has(file.type)) {
      return 'Choose a JPG, PNG, or WebP image.'
    }
    if (file.size > maximumImageBytes) {
      return 'Choose an image no larger than 5 MB.'
    }
    return ''
  }

  const selectFile = (file: File) => {
    const validationError = validateFile(file)
    if (validationError) {
      setError(validationError)
      setRecoveryAction('none')
      setStage('idle')
      if (inputRef.current) inputRef.current.value = ''
      return
    }
    void upload(file)
  }

  const upload = async (file: File) => {
    if (preview) URL.revokeObjectURL(preview)
    setPreview(URL.createObjectURL(file)); setError(''); setRecoveryAction('none'); setStage('uploading')
    const form = new FormData(); form.append('image', file)
    try {
      const draft = await apiRequest<ClothingUpload>('/wardrobe/items/upload', { method: 'POST', body: form })
      setAnalysisToken(draft.analysis_token)
      setItem(draft)
      await runAnalysis(draft, draft.analysis_token)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed.')
      setStage('error')
    }
  }

  const choose = (event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; if (file) selectFile(file) }
  const drop = (event: DragEvent) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) selectFile(file) }
  const change = (field: keyof ClothingItem, value: string) => {
    setItem(current => current ? { ...current, [field]: value } : current)
    if (field === 'name' || field === 'color' || field === 'description') {
      setFieldErrors(current => ({ ...current, [field]: undefined }))
    }
  }

  const save = async () => {
    if (!item) return
    const name = item.name.trim()
    const color = item.color.trim()
    const description = item.description?.trim() || null
    const validationErrors: FieldErrors = {}
    if (!name) validationErrors.name = 'Enter a name.'
    else if (name.length > 100) validationErrors.name = 'Use 100 characters or fewer.'
    if (!color) validationErrors.color = 'Enter a colour.'
    else if (color.length > 50) validationErrors.color = 'Use 50 characters or fewer.'
    if (description && description.length > 500) {
      validationErrors.description = 'Use 500 characters or fewer.'
    }
    setFieldErrors(validationErrors)
    if (Object.keys(validationErrors).length > 0) return

    setSaving(true); setError('')
    try {
      await apiRequest(`/wardrobe/items/${item.id}`, { method: 'PATCH', body: JSON.stringify({ name, category: item.category, color, description }) })
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
        {stage === 'idle' && <><Intro />{error && <p role="alert" style={{ color: '#9f3a32', fontSize: 13, marginTop: 18 }}>{error}</p>}</>}
        {(stage === 'uploading' || stage === 'analyzing') && <Processing stage={stage} />}
        {stage === 'error' && <div><h2 style={sectionTitle}>Something needs attention</h2><p role="alert" style={{ color: '#9f3a32', lineHeight: 1.6, marginBottom: 24 }}>{error}</p>{item && analysisToken && recoveryAction === 'check-status' && <button onClick={() => void pollAnalysis(item, analysisToken)} style={darkButton}>Check status again</button>}{item && analysisToken && recoveryAction === 'retry-analysis' && <button onClick={() => void runAnalysis(item, analysisToken)} style={darkButton}>Try analysis again</button>}<button onClick={() => { setStage('idle'); setItem(null); setAnalysisToken(''); setError(''); setRecoveryAction('none'); setFieldErrors({}); if (inputRef.current) inputRef.current.value = '' }} style={secondaryButton}>Choose another image</button></div>}
        {stage === 'done' && item && <div><h2 style={sectionTitle}>Analysis complete</h2><div style={{ display: 'grid', gap: 14 }}>
          <Field label="Name" error={fieldErrors.name}><input value={item.name} maxLength={100} onChange={event => change('name', event.target.value)} style={fieldStyle} /></Field>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}><Field label="Category"><select value={item.category} onChange={event => change('category', event.target.value)} style={fieldStyle}>{categories.map(value => <option key={value} value={value}>{value}</option>)}</select></Field><Field label="Colour" error={fieldErrors.color}><input value={item.color} maxLength={50} onChange={event => change('color', event.target.value)} style={fieldStyle} /></Field></div>
          <Field label="Description" error={fieldErrors.description}><textarea value={item.description ?? ''} maxLength={500} onChange={event => change('description', event.target.value)} rows={4} style={fieldStyle} /></Field>
          {error && <p role="alert" style={{ color: '#9f3a32', fontSize: 13 }}>{error}</p>}
          <button disabled={saving} onClick={() => void save()} style={darkButton}>{saving ? 'Saving…' : 'Save to wardrobe'}</button>
        </div></div>}
      </div>
    </div>
  </div>
}

function Intro() { return <><h2 style={sectionTitle}>AI will handle the rest</h2><p style={{ color: '#6b6055', lineHeight: 1.7, marginBottom: 38 }}>Upload a clear photo of one clothing item. Cobaju identifies its category, colour, and description for your review.</p>{['Upload one clear item', 'Analyse visible details', 'Review and save'].map((text, index) => <div key={text} style={{ display: 'flex', gap: 18, padding: '13px 0', borderBottom: '1px solid rgba(0,0,0,.07)' }}><span style={{ color: '#c9a96e' }}>0{index + 1}</span>{text}</div>)}</> }
function Processing({ stage }: { stage: Stage }) { return <><h2 style={sectionTitle}>Processing…</h2>{['Image and record created', 'Clothing guardrail', 'Metadata analysis'].map((text, index) => <div key={text} style={{ padding: '14px 0', borderBottom: '1px solid rgba(0,0,0,.07)', color: index === 0 || stage === 'analyzing' ? '#1a1816' : '#a09080' }}>{index === 0 ? '✓ ' : '○ '}{text}</div>)}</> }
function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) { return <label style={{ fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: '#a09080' }}>{label}{children}{error && <span role="alert" style={{ display: 'block', marginTop: 5, color: '#9f3a32', letterSpacing: 0, textTransform: 'none' }}>{error}</span>}</label> }

const eyebrow = { fontSize: 11, letterSpacing: '.16em', textTransform: 'uppercase' as const, color: '#a09080', marginBottom: 16 }
const title = { fontFamily: "'Playfair Display', serif", fontSize: 'clamp(36px, 4vw, 56px)', lineHeight: 1.05 }
const sectionTitle = { fontFamily: "'Playfair Display', serif", fontSize: 28, marginBottom: 24 }
const dropzone = { width: '100%', height: 460, border: '1.5px dashed', borderRadius: 8, background: 'transparent', display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 18, cursor: 'pointer' }
const overlay = { position: 'absolute' as const, inset: 0, display: 'flex', flexDirection: 'column' as const, alignItems: 'center', justifyContent: 'center', gap: 14, background: 'rgba(247,244,239,.72)' }
const fieldStyle = { display: 'block', width: '100%', marginTop: 7, padding: '11px 12px', border: '1px solid rgba(0,0,0,.13)', borderRadius: 6, background: 'white', font: 'inherit', color: '#1a1816' }
const darkButton = { width: '100%', padding: 13, border: 0, borderRadius: 6, background: '#1a1816', color: '#f7f4ef', cursor: 'pointer', fontWeight: 600 }
const secondaryButton = { ...darkButton, marginTop: 10, background: 'transparent', color: '#1a1816', border: '1px solid rgba(0,0,0,.14)' }
const darkPill = { padding: '10px 22px', borderRadius: 999, background: '#1a1816', color: '#f7f4ef', fontSize: 12 }
