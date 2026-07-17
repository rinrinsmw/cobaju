export interface User { id: number; email: string }

export type ClothingCategory = 'top' | 'bottom' | 'dress' | 'outerwear' | 'shoes' | 'bag' | 'accessory'
export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface ClothingItem {
  id: number
  name: string
  category: ClothingCategory
  color: string
  description: string | null
  original_image_path: string | null
  analysis_completed: boolean
  processing_status: ProcessingStatus
}

export interface ProcessingResult {
  item_id: number
  status: ProcessingStatus
  analysis_completed: boolean
  needs_confirmation: boolean
}

export interface StylistResponse {
  status: 'recommendation' | 'redirected' | 'rejected'
  message: string
  owned_items: Array<{ item_id: number; category: ClothingCategory; reason: string }>
  missing_categories: Array<{ category: ClothingCategory; guidance: string }>
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export function getToken() { return window.localStorage.getItem('access_token') }

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api${path}`, { ...options, headers })
  if (!response.ok) {
    let message = 'Something went wrong. Please try again.'
    try {
      const body = await response.json() as { detail?: string | Array<{ msg: string }> }
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map(error => error.msg).join(', ')
    } catch { /* Use the safe fallback for non-JSON failures. */ }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function fetchItemImage(itemId: number): Promise<string | null> {
  const token = getToken()
  if (!token) return null
  const response = await fetch(`/api/wardrobe/items/${itemId}/image`, { headers: { Authorization: `Bearer ${token}` } })
  return response.ok ? URL.createObjectURL(await response.blob()) : null
}
