import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
})

// Mirror the access token into a cookie so <img>/AsyncImage requests (thumbnails,
// avatars, face crops) authenticate too — they can't send an Authorization header.
export function syncAuthCookie() {
  const t = localStorage.getItem('access_token')
  if (t) document.cookie = `pf_token=${t}; path=/; max-age=2592000; SameSite=Lax`
  else document.cookie = 'pf_token=; path=/; max-age=0'
}
syncAuthCookie()

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const res = await axios.post('/api/auth/refresh', null, { params: { refresh_token: refresh } })
          localStorage.setItem('access_token', res.data.access_token)
          localStorage.setItem('refresh_token', res.data.refresh_token)
          syncAuthCookie()
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`
          return api.request(error.config)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          syncAuthCookie()
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
