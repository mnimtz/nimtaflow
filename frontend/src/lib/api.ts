import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
})

// Token storage: "remember me" → localStorage (persists across browser restarts),
// otherwise sessionStorage (cleared when the browser closes). Reads check both so
// the rest of the app doesn't care which was used.
export function getToken(): string | null {
  return localStorage.getItem('access_token') || sessionStorage.getItem('access_token')
}
function getRefresh(): string | null {
  return localStorage.getItem('refresh_token') || sessionStorage.getItem('refresh_token')
}
/** Persist tokens to the chosen storage (and clear the other). */
export function setTokens(access: string, refresh: string, remember = true) {
  const keep = remember ? localStorage : sessionStorage
  const drop = remember ? sessionStorage : localStorage
  keep.setItem('access_token', access); keep.setItem('refresh_token', refresh)
  drop.removeItem('access_token'); drop.removeItem('refresh_token')
  syncAuthCookie()
  window.dispatchEvent(new Event('pf-auth'))   // App.tsx schaltet reaktiv auf „eingeloggt"
}
export function clearTokens() {
  for (const s of [localStorage, sessionStorage]) {
    s.removeItem('access_token'); s.removeItem('refresh_token')
  }
  syncAuthCookie()
  window.dispatchEvent(new Event('pf-auth'))   // reaktiv ausloggen
}

// Mirror the access token into a cookie so <img>/AsyncImage requests (thumbnails,
// avatars, face crops) authenticate too — they can't send an Authorization header.
export function syncAuthCookie() {
  const t = getToken()
  if (t) document.cookie = `pf_token=${t}; path=/; max-age=2592000; SameSite=Lax`
  else document.cookie = 'pf_token=; path=/; max-age=0'
}
syncAuthCookie()

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = getRefresh()
      if (refresh) {
        // Preserve the user's "remember me" choice on refresh.
        const remember = !!localStorage.getItem('refresh_token')
        try {
          const res = await axios.post('/api/auth/refresh', null, { params: { refresh_token: refresh } })
          setTokens(res.data.access_token, res.data.refresh_token, remember)
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`
          return api.request(error.config)
        } catch {
          clearTokens()
          if (window.location.pathname !== '/login') window.location.href = '/login'
        }
      } else if (window.location.pathname !== '/login') {
        // No session at all (e.g. a phone that never logged in) and the server
        // enforces auth → send the user to the login page instead of leaving a
        // blank, content-less app that looks like a fresh install.
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export type Photo = {
  id: number
  path: string
  filename: string
  taken_at: string | null
  width: number | null
  height: number | null
  latitude: number | null
  longitude: number | null
  status: string
  thumb_small: string | null
  thumb_medium: string | null
  processed_at?: string | null
  is_video: boolean
  duration_seconds: number | null
  is_favorite: boolean
  is_archived: boolean
  is_trashed: boolean
  user_rating: number | null
  focus_x?: number | null
  focus_y?: number | null
  blur_data?: string | null
}

/** Thumbnail URL with a cache-bust token.
 * The endpoint serves with max-age=1y, so without a version a regenerated
 * thumbnail (e.g. after reprocess) would never be re-fetched by the browser.
 * `processed_at` changes on every (re)process, so the URL changes with it. */
export function thumbUrl(
  photo: { id: number; processed_at?: string | null },
  size: 'small' | 'medium' | 'large' = 'medium',
): string {
  const v = photo.processed_at ? Date.parse(photo.processed_at) : 0
  return `/api/photos/${photo.id}/thumbnail?size=${size}&v=${v}`
}

export type TimelineGroup = {
  date: string
  count: number
  photos: Photo[]
}

export type PhotoStats = {
  total: number
  videos: number
  favorites: number
  with_gps: number
  cameras: { model: string; count: number }[]
  date_min: string | null
  date_max: string | null
}

export type Person = {
  id: number
  name: string
  alias: string | null
  birthdate: string | null
  relationship_type: string | null
  profile_face_id: number | null
  face_count?: number
}

export type Source = {
  id: number
  path: string
  name: string | null
  enabled: boolean
  watch_enabled: boolean
  recursive: boolean
  exclusion_patterns: string | null
  locked: boolean
  scan_interval_minutes: number
  detect_deletions: boolean
  ai_provider: string | null
  last_scan_at: string | null
  last_scan_count: number | null
}

export type Job = {
  id: number
  name: string
  status: string
  total: number
  processed: number
  errors: number
  skipped: number
  api_cost_usd: number
  speed_per_min: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}
