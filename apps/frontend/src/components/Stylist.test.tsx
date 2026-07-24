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

async function waitForElement<T extends Element>(selector: string): Promise<T> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const element = document.querySelector<T>(selector)
    if (element) return element
    await act(
      async () => new Promise((resolve) => window.setTimeout(resolve, 0)),
    )
  }
  throw new Error(`Element not found: ${selector}`)
}

describe("Stylist session UI", () => {
  let root: Root | undefined

  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

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

  it("shows the total wardrobe count with a confirmed-item breakdown", async () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      id: index + 1,
      name: `Item ${index + 1}`,
      category: "top",
      color: "black",
      description: null,
      original_image_path: null,
      analysis_completed: true,
      processing_status: index === 9 ? "pending" : "completed",
    }))
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/wardrobe/items") return jsonResponse(items)
      throw new Error(`Unexpected request: ${String(input)}`)
    })
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

    let liveWardrobeCard: HTMLElement | null | undefined
    for (let attempt = 0; attempt < 20; attempt += 1) {
      const liveWardrobeLabel = [...container.querySelectorAll("p")].find(
        (element) => element.textContent === "Live wardrobe",
      )
      liveWardrobeCard = liveWardrobeLabel?.parentElement
      if (liveWardrobeCard?.textContent?.includes("10")) break
      await act(
        async () => new Promise((resolve) => window.setTimeout(resolve, 0)),
      )
    }
    expect(liveWardrobeCard?.textContent).toContain("10")
    expect(liveWardrobeCard?.textContent).toContain(
      "9 confirmed for styling · 1 awaiting confirmation",
    )
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

  it("saves a recommendation only after Save to Lookbook is clicked", async () => {
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
            message: "Wear your blue shirt.",
            owned_items: [],
            missing_categories: [],
            lookbook_save_token: "signed-save-receipt",
          })
        }
        if (path === "/api/recommendations" && options?.method === "POST") {
          return jsonResponse({ id: 42 })
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
    await act(
      async () => new Promise((resolve) => window.setTimeout(resolve, 0)),
    )

    expect(
      fetchMock.mock.calls.filter(
        ([path, options]) =>
          String(path) === "/api/recommendations" &&
          (options as RequestInit | undefined)?.method === "POST",
      ),
    ).toHaveLength(0)

    await act(async () => button("Save to Lookbook").click())
    await act(
      async () => new Promise((resolve) => window.setTimeout(resolve, 0)),
    )

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/recommendations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          save_token: "signed-save-receipt",
          display_title: "Work",
        }),
      }),
    )
    expect(document.body.textContent).toContain("Saved to Lookbook")
  })

  it("renders cached wardrobe images and falls back to the category emoji", async () => {
    window.localStorage.setItem("access_token", "valid-token")
    let resolveImage: ((response: Response) => void) | undefined
    const fetchMock = vi.fn(
      (input: RequestInfo | URL, options?: RequestInit) => {
        const path = String(input)
        if (path === "/api/wardrobe/items") {
          return Promise.resolve(
            jsonResponse([
              {
                id: 1,
                name: "Blue shirt",
                category: "top",
                color: "blue",
                description: null,
                original_image_path: "7/blue-shirt.jpg",
                analysis_completed: true,
                processing_status: "completed",
              },
              {
                id: 2,
                name: "Black trousers",
                category: "bottom",
                color: "black",
                description: null,
                original_image_path: null,
                analysis_completed: true,
                processing_status: "completed",
              },
            ]),
          )
        }
        if (
          path === "/api/chat/recommendations" &&
          options?.method === "POST"
        ) {
          return Promise.resolve(
            jsonResponse({
              status: "recommendation",
              message: "Wear your blue shirt with black trousers.",
              owned_items: [
                { item_id: 1, category: "top", reason: "Polished base" },
                { item_id: 2, category: "bottom", reason: "Smart contrast" },
              ],
              missing_categories: [],
            }),
          )
        }
        if (path === "/api/wardrobe/items/1/image") {
          return new Promise<Response>((resolve) => {
            resolveImage = resolve
          })
        }
        throw new Error(`Unexpected request: ${path}`)
      },
    )
    vi.stubGlobal("fetch", fetchMock)
    const createObjectURL = vi.fn(() => "blob:blue-shirt")
    class TestURL extends URL {}
    Object.defineProperties(TestURL, {
      createObjectURL: { value: createObjectURL },
      revokeObjectURL: { value: vi.fn() },
    })
    vi.stubGlobal("URL", TestURL)
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
      button("💼 Work").click()
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    expect(
      document.querySelector('[aria-label="Loading Blue shirt image"]'),
    ).not.toBeNull()
    expect(
      document.querySelector(
        '[aria-label="Black trousers image unavailable"]',
      )?.textContent,
    ).toBe("👖")
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => String(input) === "/api/wardrobe/items",
      ),
    ).toHaveLength(1)
    expect(
      fetchMock.mock.calls.filter(
        ([input]) => String(input) === "/api/wardrobe/items/1/image",
      ),
    ).toHaveLength(1)

    await act(async () => {
      resolveImage?.(
        new Response("image bytes", {
          headers: { "Content-Type": "image/jpeg" },
        }),
      )
      await new Promise((resolve) => window.setTimeout(resolve, 0))
    })

    const image = await waitForElement<HTMLImageElement>(
      'img[alt="Blue shirt"]',
    )
    expect(image.src).toContain("blob:blue-shirt")
    expect(image.style.objectFit).toBe("cover")
    expect(image.parentElement?.style.borderRadius).toBe("8px")
    expect(image.parentElement?.title).toBe("Hover to view the full image")

    await act(async () =>
      image.parentElement?.dispatchEvent(
        new MouseEvent("mouseover", { bubbles: true }),
      ),
    )
    expect(image.style.objectFit).toBe("contain")

    await act(async () =>
      image.parentElement?.dispatchEvent(
        new MouseEvent("mouseout", { bubbles: true }),
      ),
    )
    expect(image.style.objectFit).toBe("cover")

    await act(async () => image?.dispatchEvent(new Event("error")))
    expect(
      document.querySelector('[aria-label="Blue shirt image unavailable"]')
        ?.textContent,
    ).toBe("👔")
    expect(document.querySelector('img[alt="Blue shirt"]')).toBeNull()
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
    expect(document.querySelector('[role="status"]')?.textContent).toContain(
      "Wardrobe Stylist",
    )
    expect(document.body.textContent).not.toContain("Choosing shoes")

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
    const requests: Array<{ message: string }> = []
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
          const request = JSON.parse(String(options.body)) as { message: string }
          requests.push(request)
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
      { message: "Choose a fun, polished outfit for a party." },
      { message: "Make the previous recommendation more casual." },
    ])
    expect(document.body.textContent).toContain(
      "Choose a fun, polished outfit for a party.",
    )
    expect(document.body.textContent).toContain(
      "Make the previous recommendation more casual.",
    )
  })
})
