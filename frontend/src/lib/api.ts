import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
})

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
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`
          return api.request(error.config)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
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
  is_video: boolean
  duration_seconds: number | null
  is_favorite: boolean
  is_archived: boolean
  is_trashed: boolean
  user_rating: number | null
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
