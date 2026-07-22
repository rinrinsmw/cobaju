import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  apiRequest,
  type ClothingCategory,
  type ClothingItem,
  type StylistResponse,
} from "../api"
import { useAuth } from "../auth"
import {
  clearStylistSession,
  loadStylistSession,
  saveStylistSession,
  type ChatMessage,
} from "../stylistSession"

interface Props {
  prefill?: string
}

const quickPrompts = [
  { label: "💼 Work", prompt: "Help me choose a polished outfit for work." },
  {
    label: "❤️ First Date",
    prompt: "Style me for a first date that feels confident and effortless.",
  },
  { label: "☕ Coffee", prompt: "Put together a relaxed outfit for coffee." },
  { label: "🎉 Party", prompt: "Choose a fun, polished outfit for a party." },
  {
    label: "✈️ Travel",
    prompt: "Build me a comfortable, stylish travel outfit.",
  },
  {
    label: "🎓 Graduation",
    prompt: "Help me dress for a graduation celebration.",
  },
]

const followUpPrompts = [
  {
    label: "🔄 Another Outfit",
    prompt: "Give me another outfit option for the same occasion.",
  },
  {
    label: "😌 More Casual",
    prompt: "Make the previous recommendation more casual.",
  },
  {
    label: "✨ More Elegant",
    prompt: "Make the previous recommendation more elegant.",
  },
]

const loadingMessages = [
  "Looking through your wardrobe...",
  "Matching colors...",
  "Choosing shoes...",
  "Building your outfit...",
]

const emoji: Record<ClothingCategory, string> = {
  top: "👔",
  bottom: "👖",
  dress: "👗",
  outerwear: "🧥",
  shoes: "👞",
  bag: "👜",
  accessory: "⌚",
}

type RecommendedItem = StylistResponse["owned_items"][number]

function conciseExplanation(message: string) {
  return message
    .trim()
    .split(/(?<=[.!?])\s+/)
    .slice(0, 3)
    .join(" ")
}

function wardrobeTip(guidance: string) {
  return guidance.replace(/^Not owned:\s*/i, "").trim()
}

function Welcome({
  disabled,
  onSelect,
}: {
  disabled: boolean
  onSelect: (prompt: string) => void
}) {
  return (
    <section style={welcomeCard}>
      <div style={{ fontSize: 28, marginBottom: 16 }}>✨</div>
      <h2
        style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: "clamp(28px, 4vw, 40px)",
          lineHeight: 1.1,
          marginBottom: 16,
        }}
      >
        Welcome back!
      </h2>
      <p
        style={{
          fontSize: 17,
          lineHeight: 1.65,
          color: "#3f3933",
          maxWidth: 560,
          margin: "0 auto",
        }}
      >
        I'm Cobaju, your personal wardrobe stylist.
        <br />
        I'll recommend outfits using only the clothes you already own.
      </p>
      <p
        style={{
          fontFamily: "'Playfair Display', serif",
          fontSize: 21,
          margin: "26px 0 18px",
        }}
      >
        What are you dressing for today?
      </p>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          gap: 10,
        }}
      >
        {quickPrompts.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => onSelect(item.prompt)}
            disabled={disabled}
            style={chipButton}
          >
            {item.label}
          </button>
        ))}
      </div>
    </section>
  )
}

function OutfitGroup({
  title,
  items,
  itemName,
  subtle = false,
}: {
  title: string
  items: RecommendedItem[]
  itemName: (id: number) => string
  subtle?: boolean
}) {
  if (items.length === 0) return null
  return (
    <section style={{ marginTop: 22, opacity: subtle ? 0.78 : 1 }}>
      <h4
        style={{
          fontSize: 11,
          letterSpacing: ".11em",
          textTransform: "uppercase",
          color: subtle ? "#8b7f73" : "#6b6055",
          marginBottom: 10,
        }}
      >
        {title}
      </h4>
      <div
        className="outfit-item-grid"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.min(3, items.length)}, minmax(0, 1fr))`,
          gap: 10,
        }}
      >
        {items.map((item) => (
          <article
            key={item.item_id}
            style={{
              background: subtle ? "#faf8f4" : "#f5f1ea",
              border: "1px solid rgba(26,24,22,.06)",
              padding: "18px 14px",
              borderRadius: 10,
              textAlign: "center",
            }}
          >
            <div
              aria-hidden="true"
              style={{ fontSize: subtle ? 25 : 31, marginBottom: 8 }}
            >
              {emoji[item.category]}
            </div>
            <strong
              style={{ display: "block", fontSize: 13, lineHeight: 1.35 }}
            >
              {itemName(item.item_id)}
            </strong>
            <span
              style={{
                display: "block",
                fontSize: 11,
                lineHeight: 1.45,
                color: "#6b6055",
                marginTop: 5,
              }}
            >
              {item.reason}
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}

function RecommendationCard({
  response,
  itemName,
  loading,
  onFollowUp,
}: {
  response: StylistResponse
  itemName: (id: number) => string
  loading: boolean
  onFollowUp: (prompt: string) => void
}) {
  if (response.status !== "recommendation") {
    return (
      <div style={{ ...bubble, background: "#f7f4ef", color: "#1a1816" }}>
        {response.message}
      </div>
    )
  }

  const main = response.owned_items.filter((item) =>
    ["top", "bottom", "dress"].includes(item.category),
  )
  const layers = response.owned_items.filter(
    (item) => item.category === "outerwear",
  )
  const footwear = response.owned_items.filter(
    (item) => item.category === "shoes",
  )
  const accessories = response.owned_items.filter(
    (item) => item.category === "bag" || item.category === "accessory",
  )

  return (
    <article style={recommendationCard}>
      <header
        style={{
          background: "#1a1816",
          color: "#f7f4ef",
          padding: "20px 22px",
        }}
      >
        <p
          style={{
            color: "#c9a96e",
            fontSize: 11,
            letterSpacing: ".12em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          Your look
        </p>
        <h3
          style={{
            fontFamily: "'Playfair Display', serif",
            fontSize: 25,
            fontWeight: 400,
          }}
        >
          ✨ Here's what I'd wear
        </h3>
      </header>
      <div style={{ padding: "4px 22px 22px" }}>
        <OutfitGroup title="Main Outfit" items={main} itemName={itemName} />
        <OutfitGroup title="Layer" items={layers} itemName={itemName} />
        <OutfitGroup title="Footwear" items={footwear} itemName={itemName} />
        <OutfitGroup
          title="Optional Accessories"
          items={accessories}
          itemName={itemName}
          subtle
        />

        <section
          style={{
            borderTop: "1px solid rgba(26,24,22,.09)",
            marginTop: 24,
            paddingTop: 20,
          }}
        >
          <h4 style={sectionTitle}>Why this works</h4>
          <p style={{ color: "#403a34", fontSize: 14, lineHeight: 1.7 }}>
            {conciseExplanation(response.message)}
          </p>
        </section>

        {response.missing_categories.length > 0 && (
          <section style={tipCard}>
            <h4 style={{ ...sectionTitle, color: "#7a5d2d" }}>Wardrobe Tip</h4>
            {response.missing_categories.map((item) => (
              <p
                key={item.category}
                style={{ fontSize: 13, lineHeight: 1.6, color: "#6b5229" }}
              >
                {wardrobeTip(item.guidance)}
              </p>
            ))}
          </section>
        )}

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            borderTop: "1px solid rgba(26,24,22,.09)",
            marginTop: 22,
            paddingTop: 18,
          }}
        >
          {followUpPrompts.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => onFollowUp(item.prompt)}
              disabled={loading}
              style={followUpButton}
            >
              {item.label}
            </button>
          ))}
          <button
            type="button"
            disabled
            title="Validated recommendations are saved automatically"
            style={{
              ...followUpButton,
              color: "#6d5632",
              background: "#f1e9db",
            }}
          >
            ❤️ Save to Lookbook
          </button>
        </div>
      </div>
    </article>
  )
}

function LoadingMessage() {
  const [messageIndex, setMessageIndex] = useState(0)

  useEffect(() => {
    const interval = window.setInterval(
      () =>
        setMessageIndex((current) => (current + 1) % loadingMessages.length),
      1400,
    )
    return () => window.clearInterval(interval)
  }, [])

  return (
    <div
      role="status"
      aria-live="polite"
      style={{ display: "flex", alignItems: "center", gap: 10 }}
    >
      <span style={avatar}>✦</span>
      <span
        style={{
          ...bubble,
          background: "#f7f4ef",
          color: "#786e64",
          minWidth: 220,
        }}
      >
        {loadingMessages[messageIndex]}
        <span className="stylist-shimmer" aria-hidden="true" />
      </span>
    </div>
  )
}

export default function Stylist({ prefill = "" }: Props) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [initialSession] = useState(() =>
    user ? loadStylistSession(user.id) : null,
  )
  const [messages, setMessages] = useState<ChatMessage[]>(
    () => initialSession?.messages ?? [],
  )
  const [input, setInput] = useState(prefill)
  const [temporaryError, setTemporaryError] = useState("")
  const [showNewRequestDialog, setShowNewRequestDialog] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const conversationIdRef = useRef(0)
  const skipInitialPersistenceRef = useRef(Boolean(initialSession))
  const wardrobe = useQuery({
    queryKey: ["wardrobe"],
    queryFn: () => apiRequest<ClothingItem[]>("/wardrobe/items"),
  })
  const chat = useMutation({
    mutationFn: async ({
      message,
      conversationId,
    }: {
      message: string
      conversationId: number
    }) => ({
      response: await apiRequest<StylistResponse>("/chat/recommendations", {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
      conversationId,
    }),
    onSuccess: ({ response, conversationId }) => {
      if (conversationId !== conversationIdRef.current) return
      setMessages((current) => [...current, { role: "ai", response }])
      if (response.status === "recommendation")
        queryClient.invalidateQueries({ queryKey: ["history"] })
    },
    onError: (error, { conversationId }) => {
      if (conversationId === conversationIdRef.current)
        setTemporaryError(error.message)
    },
  })

  const send = (value?: string) => {
    const message = (value ?? input).trim()
    if (!message || chat.isPending) return
    setInput("")
    setTemporaryError("")
    setMessages((current) => [...current, { role: "user", text: message }])
    chat.mutate({ message, conversationId: conversationIdRef.current })
  }

  const resetConversation = () => {
    conversationIdRef.current += 1
    setMessages([])
    setInput("")
    setTemporaryError("")
    setShowNewRequestDialog(false)
    chat.reset()
    if (user) clearStylistSession(user.id)
  }

  const hasConversation = messages.some(
    (message) => message.role === "user" || message.response,
  )
  const hasStylistResponse = messages.some((message) => message.response)
  const startNewRequest = () =>
    hasConversation ? setShowNewRequestDialog(true) : resetConversation()

  useEffect(() => {
    if (prefill) {
      const timer = window.setTimeout(() => send(prefill), 300)
      return () => window.clearTimeout(timer)
    }
  }, [])
  useEffect(() => {
    if (!user) return
    if (skipInitialPersistenceRef.current) {
      skipInitialPersistenceRef.current = false
      return
    }
    if (hasConversation) saveStylistSession(user.id, messages)
    else clearStylistSession(user.id)
  }, [hasConversation, messages, user])
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages, chat.isPending])

  const itemName = (id: number) =>
    wardrobe.data?.find((item) => item.id === id)?.name ?? "Wardrobe piece"

  return (
    <div style={{ paddingTop: 64, background: "#f7f4ef", minHeight: "100vh" }}>
      <div
        className="page-header"
        style={{ background: "#100f0d", padding: "72px 60px 56px" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 24,
          }}
        >
          <div>
            <p style={eyebrow}>Your personal stylist</p>
            <h1 style={title}>
              Dress for the moment.
              <br />
              <em style={{ color: "#c9a96e" }}>Use what you own.</em>
            </h1>
          </div>
          <button onClick={startNewRequest} style={newRequestButton}>
            ＋ New Request
          </button>
        </div>
      </div>
      <div
        className="stylist-layout page-content"
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "48px 60px",
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 300px",
          gap: 32,
        }}
      >
        <main
          style={{
            background: "white",
            borderRadius: 12,
            border: "1px solid rgba(0,0,0,.08)",
            minHeight: 590,
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 10px 35px rgba(35,28,20,.05)",
          }}
        >
          <div
            ref={logRef}
            style={{
              flex: 1,
              overflowY: "auto",
              maxHeight: 650,
              padding: 28,
              display: "flex",
              flexDirection: "column",
              gap: 20,
            }}
          >
            {(!hasConversation || (chat.isPending && !hasStylistResponse)) && (
              <Welcome disabled={chat.isPending} onSelect={send} />
            )}
            {messages.map((message, index) => (
              <div
                key={index}
                style={{
                  display: "flex",
                  justifyContent:
                    message.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                {message.role === "ai" && <span style={avatar}>✦</span>}
                <div
                  style={{
                    maxWidth:
                      message.response?.status === "recommendation"
                        ? "94%"
                        : "82%",
                    minWidth: 0,
                  }}
                >
                  {message.text && (
                    <div
                      style={{
                        ...bubble,
                        background:
                          message.role === "user" ? "#1a1816" : "#f7f4ef",
                        color: message.role === "user" ? "#f0ece4" : "#1a1816",
                      }}
                    >
                      {message.text}
                    </div>
                  )}
                  {message.response && (
                    <RecommendationCard
                      response={message.response}
                      itemName={itemName}
                      loading={chat.isPending}
                      onFollowUp={send}
                    />
                  )}
                </div>
              </div>
            ))}
            {chat.isPending && <LoadingMessage />}
            {temporaryError && (
              <div
                role="alert"
                style={{ display: "flex", alignItems: "center", gap: 10 }}
              >
                <span style={avatar}>✦</span>
                <span
                  style={{ ...bubble, background: "#f7f4ef", color: "#9f3a32" }}
                >
                  {temporaryError}
                </span>
              </div>
            )}
          </div>
          <div
            style={{
              padding: 16,
              borderTop: "1px solid rgba(0,0,0,.07)",
              display: "flex",
              gap: 10,
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") send()
              }}
              disabled={chat.isPending}
              placeholder="What are you dressing for?"
              aria-label="Styling request"
              style={composer}
            />
            <button
              onClick={() => send()}
              disabled={chat.isPending}
              style={sendButton}
            >
              Send
            </button>
          </div>
        </main>
        <aside style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={sideCard}>
            <p style={sideTitle}>Live wardrobe</p>
            <p
              style={{ fontFamily: "'Playfair Display', serif", fontSize: 36 }}
            >
              {wardrobe.isPending
                ? "…"
                : (wardrobe.data?.filter(
                    (item) => item.processing_status === "completed",
                  ).length ?? 0)}
            </p>
            <p style={{ color: "#6b6055", fontSize: 12, lineHeight: 1.55 }}>
              confirmed pieces available to your stylist
            </p>
          </div>
          <div
            style={{
              ...sideCard,
              background: "#ece3d5",
              borderColor: "transparent",
            }}
          >
            <p
              style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 19,
                marginBottom: 9,
              }}
            >
              Styled from your wardrobe
            </p>
            <p style={{ color: "#6b6055", fontSize: 12, lineHeight: 1.65 }}>
              Cobaju only selects confirmed pieces you already own. Helpful
              additions are clearly marked as wardrobe tips.
            </p>
          </div>
        </aside>
      </div>
      {showNewRequestDialog && (
        <div
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget)
              setShowNewRequestDialog(false)
          }}
          style={dialogBackdrop}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-request-title"
            aria-describedby="new-request-description"
            style={dialogCard}
          >
            <h2
              id="new-request-title"
              style={{
                fontFamily: "'Playfair Display', serif",
                fontSize: 25,
                marginBottom: 10,
              }}
            >
              Start a new styling request?
            </h2>
            <p
              id="new-request-description"
              style={{ color: "#6b6055", fontSize: 14, marginBottom: 26 }}
            >
              Your current conversation will be cleared.
            </p>
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}
            >
              <button
                onClick={() => setShowNewRequestDialog(false)}
                style={dialogCancelButton}
              >
                Cancel
              </button>
              <button onClick={resetConversation} style={dialogConfirmButton}>
                Start New Request
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const eyebrow = {
  fontSize: 11,
  letterSpacing: ".16em",
  textTransform: "uppercase" as const,
  color: "rgba(255,255,255,.4)",
  marginBottom: 16,
}
const title = {
  fontFamily: "'Playfair Display', serif",
  fontSize: "clamp(34px, 5vw, 58px)",
  lineHeight: 1.05,
  color: "#f0ece4",
  fontWeight: 400,
}
const avatar = {
  width: 30,
  height: 30,
  borderRadius: "50%",
  flexShrink: 0,
  background: "#1a1816",
  color: "#c9a96e",
  display: "grid",
  placeItems: "center",
  marginRight: 10,
}
const bubble = {
  padding: "12px 16px",
  borderRadius: 10,
  fontSize: 14,
  lineHeight: 1.6,
}
const welcomeCard = {
  margin: "auto",
  width: "100%",
  padding: "46px 28px",
  borderRadius: 12,
  textAlign: "center" as const,
  background: "linear-gradient(145deg, #faf8f4 0%, #f1e9dd 100%)",
  border: "1px solid rgba(125,98,61,.1)",
}
const chipButton = {
  padding: "10px 15px",
  border: "1px solid rgba(26,24,22,.12)",
  borderRadius: 999,
  background: "#fff",
  color: "#1a1816",
  font: "inherit",
  fontSize: 13,
  cursor: "pointer",
}
const recommendationCard = {
  border: "1px solid rgba(26,24,22,.11)",
  borderRadius: 12,
  overflow: "hidden",
  background: "#fff",
  boxShadow: "0 9px 28px rgba(35,28,20,.07)",
}
const sectionTitle = {
  fontFamily: "'Playfair Display', serif",
  fontSize: 18,
  marginBottom: 9,
}
const tipCard = {
  background: "#faf3e5",
  border: "1px solid rgba(154,119,61,.15)",
  borderRadius: 9,
  marginTop: 18,
  padding: "16px 18px",
}
const followUpButton = {
  padding: "9px 12px",
  border: "1px solid rgba(26,24,22,.1)",
  borderRadius: 999,
  background: "#f7f4ef",
  color: "#302b27",
  font: "inherit",
  fontSize: 11,
  cursor: "pointer",
}
const composer = {
  flex: 1,
  minWidth: 0,
  padding: "12px 17px",
  border: "1px solid rgba(0,0,0,.1)",
  borderRadius: 999,
  background: "#f7f4ef",
  font: "inherit",
}
const sendButton = {
  padding: "11px 22px",
  border: 0,
  borderRadius: 999,
  background: "#1a1816",
  color: "#f7f4ef",
  cursor: "pointer",
}
const sideCard = {
  background: "white",
  borderRadius: 10,
  padding: 22,
  border: "1px solid rgba(0,0,0,.08)",
}
const sideTitle = {
  fontSize: 11,
  letterSpacing: ".1em",
  textTransform: "uppercase" as const,
  color: "#a09080",
  marginBottom: 14,
}
const newRequestButton = {
  flexShrink: 0,
  marginTop: 4,
  padding: "10px 18px",
  borderRadius: 999,
  border: "1px solid rgba(255,255,255,.28)",
  background: "rgba(255,255,255,.08)",
  color: "#f0ece4",
  font: "inherit",
  fontSize: 13,
  cursor: "pointer",
}
const dialogBackdrop = {
  position: "fixed" as const,
  inset: 0,
  zIndex: 200,
  background: "rgba(16,15,13,.62)",
  display: "grid",
  placeItems: "center",
  padding: 24,
}
const dialogCard = {
  width: "min(100%, 420px)",
  background: "#fff",
  borderRadius: 10,
  padding: 28,
  boxShadow: "0 20px 60px rgba(0,0,0,.25)",
}
const dialogCancelButton = {
  padding: "10px 17px",
  borderRadius: 999,
  border: "1px solid rgba(0,0,0,.14)",
  background: "#fff",
  color: "#1a1816",
  font: "inherit",
  cursor: "pointer",
}
const dialogConfirmButton = {
  padding: "10px 17px",
  borderRadius: 999,
  border: "1px solid #1a1816",
  background: "#1a1816",
  color: "#f7f4ef",
  font: "inherit",
  cursor: "pointer",
}
