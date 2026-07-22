import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import Stylist from "./Stylist"
import { getStylistSessionKey, saveStylistSession } from "../stylistSession"

vi.mock("../auth", () => ({
  useAuth: () => ({ user: { id: 7, email: "stylist@example.com" } }),
}))

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

async function renderStylist(): Promise<Root> {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])))
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)

  await act(async () => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <Stylist />
      </QueryClientProvider>,
    )
    await new Promise((resolve) => window.setTimeout(resolve, 0))
  })
  return root
}

function button(label: string) {
  const match = [...document.querySelectorAll("button")].find((element) =>
    element.textContent?.includes(label),
  )
  if (!match) throw new Error(`Button not found: ${label}`)
  return match as HTMLButtonElement
}

describe("Stylist session UI", () => {
  let root: Root | undefined

  beforeEach(() => window.sessionStorage.clear())

  afterEach(async () => {
    if (root) await act(async () => root?.unmount())
    root = undefined
    vi.unstubAllGlobals()
  })

  it("restores saved completed messages and clears them after confirmation", async () => {
    const savedAt = Date.now() - 60_000
    saveStylistSession(
      7,
      [
        { role: "ai", text: "Welcome back" },
        { role: "user", text: "An outfit for dinner" },
        { role: "ai", text: "Try your navy shirt." },
      ],
      savedAt,
    )
    root = await renderStylist()

    expect(document.body.textContent).toContain("An outfit for dinner")
    expect(document.body.textContent).toContain("Try your navy shirt.")
    expect(
      JSON.parse(window.sessionStorage.getItem(getStylistSessionKey(7)) ?? "{}")
        .updatedAt,
    ).toBe(new Date(savedAt).toISOString())

    await act(async () => button("New Request").click())
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(document.body.textContent).toContain(
      "Your current conversation will be cleared.",
    )

    await act(async () => button("Start New Request").click())
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(document.body.textContent).not.toContain("An outfit for dinner")
    expect(document.body.textContent).toContain("Welcome back!")
    expect(document.body.textContent).toContain(
      "What are you dressing for today?",
    )
    expect(window.sessionStorage.getItem(getStylistSessionKey(7))).toBeNull()
  })

  it("returns directly to the welcome state when the conversation is empty", async () => {
    root = await renderStylist()

    await act(async () => button("New Request").click())

    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(window.sessionStorage.getItem(getStylistSessionKey(7))).toBeNull()
  })

  it("returns a recommendation after the user manually sends a request", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) => {
        const path = String(input)
        if (path === "/api/wardrobe/items") return jsonResponse([])
        if (
          path === "/api/chat/recommendations" &&
          options?.method === "POST"
        ) {
          return jsonResponse({
            status: "recommendation",
            message: "Wear your blue shirt with tailored trousers.",
            owned_items: [],
            missing_categories: [],
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal("fetch", fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root?.render(
        <QueryClientProvider client={queryClient}>
          <Stylist />
        </QueryClientProvider>,
      )
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    const input = container.querySelector<HTMLInputElement>(
      'input[aria-label="Styling request"]',
    )
    if (!input) throw new Error("Stylist input did not render")
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value",
      )?.set
      valueSetter?.call(input, "Help me dress for an interview")
      input.dispatchEvent(new Event("input", { bubbles: true }))
    })
    await act(async () => {
      button("Send").click()
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/recommendations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ message: "Help me dress for an interview" }),
      }),
    )
    expect(document.body.textContent).toContain(
      "Wear your blue shirt with tailored trousers.",
    )
  })

  it("submits a welcome chip through the existing chat request", async () => {
    let resolveChat: ((response: Response) => void) | undefined
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, options?: RequestInit) => {
        const path = String(input)
        if (path === "/api/wardrobe/items")
          return Promise.resolve(jsonResponse([]))
        if (
          path === "/api/chat/recommendations" &&
          options?.method === "POST"
        ) {
          return new Promise<Response>((resolve) => {
            resolveChat = resolve
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal("fetch", fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root?.render(
        <QueryClientProvider client={queryClient}>
          <Stylist />
        </QueryClientProvider>,
      )
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    await act(async () => button("💼 Work").click())

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/recommendations",
      expect.objectContaining({
        body: JSON.stringify({
          message: "Help me choose a polished outfit for work.",
        }),
      }),
    )
    expect(button("Send").disabled).toBe(true)
    expect(
      container.querySelector<HTMLInputElement>(
        'input[aria-label="Styling request"]',
      )?.disabled,
    ).toBe(true)

    await act(async () => {
      resolveChat?.(
        jsonResponse({
          status: "recommendation",
          message: "A polished combination.",
          owned_items: [],
          missing_categories: [],
        }),
      )
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })
  })

  it("groups selected pieces and sends one follow-up request without clearing history", async () => {
    const requests: string[] = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, options?: RequestInit) => {
        const path = String(input)
        if (path === "/api/wardrobe/items")
          return jsonResponse([
            {
              id: 1,
              name: "Teal dress",
              category: "dress",
              color: "teal",
              description: null,
              original_image_path: null,
              analysis_completed: true,
              processing_status: "completed",
            },
            {
              id: 2,
              name: "Black blazer",
              category: "outerwear",
              color: "black",
              description: null,
              original_image_path: null,
              analysis_completed: true,
              processing_status: "completed",
            },
            {
              id: 3,
              name: "Leather loafers",
              category: "shoes",
              color: "black",
              description: null,
              original_image_path: null,
              analysis_completed: true,
              processing_status: "completed",
            },
            {
              id: 4,
              name: "Gold earrings",
              category: "accessory",
              color: "gold",
              description: null,
              original_image_path: null,
              analysis_completed: true,
              processing_status: "completed",
            },
          ])
        if (
          path === "/api/chat/recommendations" &&
          options?.method === "POST"
        ) {
          const message = JSON.parse(String(options.body)).message as string
          requests.push(message)
          return jsonResponse({
            status: "recommendation",
            message:
              "The teal dress is the statement piece. The blazer adds structure. The loafers keep it comfortable. This fourth sentence should not be displayed.",
            owned_items: [
              {
                item_id: 1,
                category: "dress",
                reason: "Confident focal point",
              },
              { item_id: 2, category: "outerwear", reason: "Adds structure" },
              { item_id: 3, category: "shoes", reason: "Polished comfort" },
              { item_id: 4, category: "accessory", reason: "Subtle finish" },
            ],
            missing_categories: [
              {
                category: "bottom",
                guidance:
                  "Not owned: Neutral tailored trousers would unlock more combinations.",
              },
            ],
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal("fetch", fetchMock)
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
    await act(async () => {
      root?.render(
        <QueryClientProvider client={queryClient}>
          <Stylist />
        </QueryClientProvider>,
      )
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })
    await act(async () => {
      button("🎉 Party").click()
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    expect(document.body.textContent).toContain("Here's what I'd wear")
    expect(document.body.textContent).toContain("Main Outfit")
    expect(document.body.textContent).toContain("Layer")
    expect(document.body.textContent).toContain("Footwear")
    expect(document.body.textContent).toContain("Optional Accessories")
    expect(document.body.textContent).toContain("Why this works")
    expect(document.body.textContent).toContain("Wardrobe Tip")
    expect(document.body.textContent).toContain(
      "Neutral tailored trousers would unlock more combinations.",
    )
    expect(document.body.textContent).not.toContain("This fourth sentence")
    expect(document.body.textContent).not.toContain("Not owned:")
    expect(document.body.textContent).not.toContain("Item #")
    expect(document.body.textContent).not.toContain("evaluation")

    await act(async () => {
      button("😌 More Casual").click()
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    expect(requests).toEqual([
      "Choose a fun, polished outfit for a party.",
      "Make the previous recommendation more casual.",
    ])
    expect(document.body.textContent).toContain(
      "Choose a fun, polished outfit for a party.",
    )
    expect(document.body.textContent).toContain(
      "Make the previous recommendation more casual.",
    )
  })
})
