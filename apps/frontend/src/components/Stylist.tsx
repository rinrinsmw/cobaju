import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, type ClothingItem, type StylistResponse } from '../api'
import { useAuth } from '../auth'
import {
  clearStylistSession,
  loadStylistSession,
  saveStylistSession,
  type ChatMessage,
} from '../stylistSession'

interface Props { prefill?: string }
const welcomeMessage: ChatMessage = { role: 'ai', text: "Tell me where you're going or what you need to wear. I'll build an outfit from your wardrobe." }
const quickPrompts = ['Interview outfit', 'Casual Friday', 'First date', 'Gallery opening', 'Weekend brunch']
const emoji: Record<string, string> = { top: '👔', bottom: '👖', dress: '👗', outerwear: '🧥', shoes: '👞', bag: '👜', accessory: '⌚' }

export default function Stylist({ prefill = '' }: Props) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [initialSession] = useState(() => user ? loadStylistSession(user.id) : null)
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    return initialSession?.messages ?? [welcomeMessage]
  })
  const [input, setInput] = useState(prefill)
  const [temporaryError, setTemporaryError] = useState('')
  const [showNewRequestDialog, setShowNewRequestDialog] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const conversationIdRef = useRef(0)
  const skipInitialPersistenceRef = useRef(Boolean(initialSession))
  const wardrobe = useQuery({ queryKey: ['wardrobe'], queryFn: () => apiRequest<ClothingItem[]>('/wardrobe/items') })
  const chat = useMutation({
    mutationFn: async ({ message, conversationId }: { message: string; conversationId: number }) => ({
      response: await apiRequest<StylistResponse>('/chat/recommendations', { method: 'POST', body: JSON.stringify({ message }) }),
      conversationId,
    }),
    onSuccess: ({ response, conversationId }) => {
      if (conversationId !== conversationIdRef.current) return
      setMessages(current => [...current, { role: 'ai', response }])
      if (response.status === 'recommendation') queryClient.invalidateQueries({ queryKey: ['history'] })
    },
    onError: (error, { conversationId }) => {
      if (conversationId === conversationIdRef.current) setTemporaryError(error.message)
    },
  })

  const send = (value?: string) => {
    const message = (value ?? input).trim()
    if (!message || chat.isPending) return
    setInput('')
    setTemporaryError('')
    setMessages(current => [...current, { role: 'user', text: message }])
    chat.mutate({ message, conversationId: conversationIdRef.current })
  }

  const resetConversation = () => {
    conversationIdRef.current += 1
    setMessages([welcomeMessage])
    setInput('')
    setTemporaryError('')
    setShowNewRequestDialog(false)
    chat.reset()
    if (user) clearStylistSession(user.id)
  }

  const hasConversation = messages.some(message => message.role === 'user' || message.response)
  const startNewRequest = () => hasConversation ? setShowNewRequestDialog(true) : resetConversation()

  useEffect(() => { if (prefill) { const timer = window.setTimeout(() => send(prefill), 300); return () => window.clearTimeout(timer) } }, [])
  useEffect(() => {
    if (!user) return
    if (skipInitialPersistenceRef.current) {
      skipInitialPersistenceRef.current = false
      return
    }
    if (hasConversation) saveStylistSession(user.id, messages)
    else clearStylistSession(user.id)
  }, [hasConversation, messages, user])
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [messages, chat.isPending])
  const itemName = (id: number) => wardrobe.data?.find(item => item.id === id)?.name ?? `Item #${id}`

  return <div style={{ paddingTop: 64, background: '#f7f4ef', minHeight: '100vh' }}>
    <div className="page-header" style={{ background: '#100f0d', padding: '72px 60px 56px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 24 }}>
        <div><p style={eyebrow}>AI Stylist</p><h1 style={title}>What are you<br /><em style={{ color: '#c9a96e' }}>dressing for?</em></h1></div>
        <button onClick={startNewRequest} style={newRequestButton}>＋ New Request</button>
      </div>
    </div>
    <div className="stylist-layout page-content" style={{ maxWidth: 1200, margin: '0 auto', padding: '48px 60px', display: 'grid', gridTemplateColumns: '1fr 340px', gap: 40 }}>
      <div style={{ background: 'white', borderRadius: 8, border: '1px solid rgba(0,0,0,.08)', minHeight: 560, display: 'flex', flexDirection: 'column' }}>
        <div ref={logRef} style={{ flex: 1, overflowY: 'auto', maxHeight: 500, padding: 28, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {messages.map((message, index) => <div key={index} style={{ display: 'flex', justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start' }}>
            {message.role === 'ai' && <span style={avatar}>✦</span>}
            <div style={{ maxWidth: '82%' }}>
              {message.text && <div style={{ ...bubble, background: message.role === 'user' ? '#1a1816' : '#f7f4ef', color: message.role === 'user' ? '#f0ece4' : '#1a1816' }}>{message.text}</div>}
              {message.response && <div style={{ border: '1px solid rgba(0,0,0,.1)', borderRadius: 8, overflow: 'hidden' }}>
                <div style={{ background: '#1a1816', color: '#f0ece4', padding: '13px 17px', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.07em' }}>{message.response.status === 'recommendation' ? 'Recommended outfit' : 'Stylist response'}</div>
                <div style={{ padding: 18 }}><p style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 14 }}>{message.response.message}</p>
                  {message.response.owned_items.length > 0 && <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(3, message.response.owned_items.length)}, 1fr)`, gap: 8 }}>
                    {message.response.owned_items.map(item => <div key={item.item_id} style={{ background: '#f7f4ef', padding: 12, borderRadius: 6, textAlign: 'center' }}><div style={{ fontSize: 28 }}>{emoji[item.category]}</div><strong style={{ display: 'block', fontSize: 11 }}>{itemName(item.item_id)}</strong><span style={{ fontSize: 10, color: '#6b6055' }}>{item.reason}</span></div>)}
                  </div>}
                  {message.response.missing_categories.map(item => <p key={item.category} style={{ fontSize: 12, color: '#9a773d', marginTop: 10 }}>Not owned: {item.category} — {item.guidance}</p>)}
                  {message.response.status === 'recommendation' && <p style={{ fontSize: 11, color: '#a09080', marginTop: 14 }}>Saved automatically to your Lookbook.</p>}
                </div>
              </div>}
            </div>
          </div>)}
          {chat.isPending && <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={avatar}>✦</span><span style={{ ...bubble, background: '#f7f4ef', color: '#a09080' }}>Searching your wardrobe<span className="dot-1"> ·</span><span className="dot-2"> ·</span><span className="dot-3"> ·</span></span></div>}
          {temporaryError && <div role="alert" style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={avatar}>✦</span><span style={{ ...bubble, background: '#f7f4ef', color: '#9f3a32' }}>{temporaryError}</span></div>}
        </div>
        <div style={{ padding: 16, borderTop: '1px solid rgba(0,0,0,.07)', display: 'flex', gap: 10 }}><input value={input} onChange={event => setInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') send() }} placeholder="Describe the occasion or look…" style={composer} /><button onClick={() => send()} disabled={chat.isPending} style={sendButton}>Send</button></div>
      </div>
      <aside style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <div style={sideCard}><p style={sideTitle}>Quick prompts</p>{quickPrompts.map(prompt => <button key={prompt} onClick={() => send(prompt)} style={promptButton}>{prompt} →</button>)}</div>
        <div style={sideCard}><p style={sideTitle}>Live wardrobe</p><p style={{ fontFamily: "'Playfair Display', serif", fontSize: 32 }}>{wardrobe.isPending ? '…' : wardrobe.data?.filter(item => item.processing_status === 'completed').length ?? 0}</p><p style={{ color: '#6b6055', fontSize: 12 }}>confirmed pieces available to the stylist</p></div>
      </aside>
    </div>
    {showNewRequestDialog && <div role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setShowNewRequestDialog(false) }} style={dialogBackdrop}>
      <div role="dialog" aria-modal="true" aria-labelledby="new-request-title" aria-describedby="new-request-description" style={dialogCard}>
        <h2 id="new-request-title" style={{ fontFamily: "'Playfair Display', serif", fontSize: 25, marginBottom: 10 }}>Start a new styling request?</h2>
        <p id="new-request-description" style={{ color: '#6b6055', fontSize: 14, marginBottom: 26 }}>Your current conversation will be cleared.</p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button onClick={() => setShowNewRequestDialog(false)} style={dialogCancelButton}>Cancel</button>
          <button onClick={resetConversation} style={dialogConfirmButton}>Start New Request</button>
        </div>
      </div>
    </div>}
  </div>
}

const eyebrow = { fontSize: 11, letterSpacing: '.16em', textTransform: 'uppercase' as const, color: 'rgba(255,255,255,.35)', marginBottom: 16 }
const title = { fontFamily: "'Playfair Display', serif", fontSize: 'clamp(36px, 5vw, 64px)', lineHeight: 1.05, color: '#f0ece4' }
const avatar = { width: 30, height: 30, borderRadius: '50%', flexShrink: 0, background: '#1a1816', color: '#c9a96e', display: 'grid', placeItems: 'center', marginRight: 10 }
const bubble = { padding: '12px 16px', borderRadius: 8, fontSize: 14, lineHeight: 1.6 }
const composer = { flex: 1, padding: '11px 16px', border: '1px solid rgba(0,0,0,.1)', borderRadius: 999, background: '#f7f4ef', font: 'inherit' }
const sendButton = { padding: '11px 22px', border: 0, borderRadius: 999, background: '#1a1816', color: '#f7f4ef', cursor: 'pointer' }
const sideCard = { background: 'white', borderRadius: 8, padding: 22, border: '1px solid rgba(0,0,0,.08)' }
const sideTitle = { fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase' as const, color: '#a09080', marginBottom: 14 }
const promptButton = { width: '100%', textAlign: 'left' as const, font: 'inherit', fontSize: 13, padding: '10px 0', border: 0, borderBottom: '1px solid rgba(0,0,0,.06)', background: 'transparent', cursor: 'pointer' }
const newRequestButton = { flexShrink: 0, marginTop: 4, padding: '10px 18px', borderRadius: 999, border: '1px solid rgba(255,255,255,.28)', background: 'rgba(255,255,255,.08)', color: '#f0ece4', font: 'inherit', fontSize: 13, cursor: 'pointer' }
const dialogBackdrop = { position: 'fixed' as const, inset: 0, zIndex: 200, background: 'rgba(16,15,13,.62)', display: 'grid', placeItems: 'center', padding: 24 }
const dialogCard = { width: 'min(100%, 420px)', background: '#fff', borderRadius: 10, padding: 28, boxShadow: '0 20px 60px rgba(0,0,0,.25)' }
const dialogCancelButton = { padding: '10px 17px', borderRadius: 999, border: '1px solid rgba(0,0,0,.14)', background: '#fff', color: '#1a1816', font: 'inherit', cursor: 'pointer' }
const dialogConfirmButton = { padding: '10px 17px', borderRadius: 999, border: '1px solid #1a1816', background: '#1a1816', color: '#f7f4ef', font: 'inherit', cursor: 'pointer' }
