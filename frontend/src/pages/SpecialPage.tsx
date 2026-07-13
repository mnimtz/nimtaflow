// v1.561: "360° & Drohne" — neuer Menüpunkt für Insta360-Panoramen und
// Drohnen-Aufnahmen (HoverAir X1 ProMax, DJI, etc.).
// - Filter-Chips 360 | Drohne
// - Grid mit speziellen Overlays (360°-Chip / Höhen-Chip)
// - 360°-Klick öffnet Sphere-Viewer (Three.js, invertierte Kugel-Textur)
// - Drohnen-Klick zeigt Höhen/Gimbal-Info als Overlay
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useT } from '../i18n'
import { Globe, Plane, X, Info } from 'lucide-react'
// @ts-ignore — three ist als runtime-dep drin, aber ohne @types/three
import * as THREE from 'three'

type Photo = {
  id: number
  filename: string
  taken_at: string | null
  city: string | null
  country: string | null
  is_video: boolean
  thumb_url: string
  thumb_medium_url: string
  original_url: string
  video_url?: string
  is_360?: boolean
  is_drone?: boolean
  drone_metadata?: {
    relative_altitude_m?: number | null
    absolute_altitude_m?: number | null
    gimbal_pitch?: number | null
    make?: string | null
    model?: string | null
    story?: string | null
  } | null
}
type PhotoPage = {
  items: Photo[]; next_cursor: number | null; has_more: boolean
  counts?: { total_360: number; total_drone: number }
}

export default function SpecialPage() {
  const { t } = useT()
  const [filter, setFilter] = useState<'all' | '360' | 'drone'>('all')
  const [viewer, setViewer] = useState<Photo | null>(null)

  const { data } = useQuery<PhotoPage>({
    queryKey: ['special', filter],
    queryFn: () => api.get('/photos/special', { params: { filter, limit: 120 } }).then(r => r.data),
    refetchOnWindowFocus: false,
  })

  const items = data?.items ?? []
  const counts = data?.counts

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <header className="mb-4">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white">360° & Drohne</h1>
        <p className="text-sm text-zinc-500">
          Panorama-Aufnahmen deiner Insta360 und Luftaufnahmen deiner HoverAir/DJI-Drohne
          — mit passendem Viewer.
        </p>
      </header>

      <div className="flex gap-2 mb-4 flex-wrap">
        <Chip active={filter === 'all'} onClick={() => setFilter('all')}
              icon={<span>Alle</span>}
              badge={counts ? counts.total_360 + counts.total_drone : undefined} />
        <Chip active={filter === '360'} onClick={() => setFilter('360')}
              icon={<><Globe size={14} /> 360°</>}
              badge={counts?.total_360} />
        <Chip active={filter === 'drone'} onClick={() => setFilter('drone')}
              icon={<><Plane size={14} /> Drohne</>}
              badge={counts?.total_drone} />
      </div>

      {items.length === 0 && (
        <div className="text-sm text-zinc-500 py-10 text-center">
          Keine Aufnahmen gefunden. Der Erkennungs-Task läuft möglicherweise noch —
          in einigen Minuten erneut prüfen.
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
        {items.map(p => (
          <Tile key={p.id} photo={p} onOpen={() => setViewer(p)} />
        ))}
      </div>

      {viewer && (
        <ViewerModal photo={viewer} onClose={() => setViewer(null)} />
      )}
    </div>
  )
}

function Chip({ active, onClick, icon, badge }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; badge?: number
}) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 rounded-full text-sm flex items-center gap-2 border transition ${
        active
          ? 'bg-indigo-600 text-white border-indigo-600'
          : 'bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 border-zinc-300 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800'
      }`}>
      <span className="flex items-center gap-1">{icon}</span>
      {badge != null && (
        <span className={`text-xs px-1.5 py-0.5 rounded-full tabular-nums ${
          active ? 'bg-white/20' : 'bg-zinc-100 dark:bg-zinc-800'
        }`}>{badge}</span>
      )}
    </button>
  )
}

function Tile({ photo, onOpen }: { photo: Photo; onOpen: () => void }) {
  const isDrone = !!photo.is_drone
  const is360 = !!photo.is_360
  const altitude = photo.drone_metadata?.relative_altitude_m
  // v1.563: für 360°-Fotos den Little-Planet als Thumbnail — visuell viel
  // erkennbarer als der verzerrte Streifen (equirectangular).
  const thumbSrc = is360 && !photo.is_video
    ? `/api/v1/photos/${photo.id}/planet`
    : photo.thumb_medium_url
  return (
    <button onClick={onOpen}
      className="group relative aspect-square rounded-xl overflow-hidden bg-zinc-200 dark:bg-zinc-800 focus:ring-2 focus:ring-indigo-500 outline-none">
      <img src={thumbSrc} alt=""
        loading="lazy"
        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
        onError={(e) => {
          // Falls Little-Planet-Rendering noch nicht durch: Fallback auf normalen Thumb
          const el = e.currentTarget
          if (el.src.includes('/planet')) el.src = photo.thumb_medium_url
        }} />
      {is360 && (
        <span className="absolute top-2 left-2 bg-black/60 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
          <Globe size={11} /> 360°
        </span>
      )}
      {isDrone && (
        <span className="absolute top-2 left-2 bg-black/60 text-white text-[10px] font-bold px-2 py-0.5 rounded-full flex items-center gap-1">
          <Plane size={11} /> {altitude != null ? `${Math.round(altitude)}m` : 'Drohne'}
        </span>
      )}
      {photo.is_video && (
        <span className="absolute top-2 right-2 bg-black/60 text-white text-[10px] px-1.5 py-0.5 rounded">▶</span>
      )}
    </button>
  )
}

function ViewerModal({ photo, onClose }: { photo: Photo; onClose: () => void }) {
  const is360 = !!photo.is_360
  const [mode, setMode] = useState<'sphere' | 'reframe'>('sphere')
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 bg-black flex items-center justify-center">
      <button onClick={onClose}
        className="absolute top-4 right-4 z-10 bg-black/50 text-white rounded-full p-2 hover:bg-black/70">
        <X size={20} />
      </button>
      {is360 && !photo.is_video && (
        <>
          <div className="absolute top-4 left-4 z-10 flex gap-2">
            <button onClick={() => setMode('sphere')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${mode==='sphere' ? 'bg-white text-black' : 'bg-black/50 text-white'}`}>
              🌍 360°-Viewer
            </button>
            <button onClick={() => setMode('reframe')}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold ${mode==='reframe' ? 'bg-white text-black' : 'bg-black/50 text-white'}`}>
              📸 Perspektiven
            </button>
          </div>
          {mode === 'sphere'
            ? <SphereViewer imageUrl={photo.original_url} />
            : <ReframeChooser photoId={photo.id} />}
        </>
      )}
      {is360 && photo.is_video && photo.video_url && (
        <SphereVideoViewer videoUrl={photo.video_url} />
      )}
      {!is360 && (
        <div className="max-w-full max-h-full">
          {photo.is_video && photo.video_url ? (
            <video src={photo.video_url} controls className="max-h-[90vh] max-w-full" />
          ) : (
            <img src={photo.original_url} className="max-h-[90vh] max-w-full object-contain" />
          )}
        </div>
      )}
      {photo.is_drone && (
        <DroneInfoOverlay photo={photo} />
      )}
    </div>
  )
}

function ReframeChooser({ photoId }: { photoId: number }) {
  // 4 Fest-Perspektiven aus dem 360° — vorne, rechts, hinten, links.
  // v0 (fest); spätere Version: VLM findet die interessantesten Winkel.
  const views = [
    { idx: 0, label: 'Vorne', hint: 'yaw 0°' },
    { idx: 1, label: 'Rechts', hint: 'yaw 90°' },
    { idx: 2, label: 'Hinten', hint: 'yaw 180°' },
    { idx: 3, label: 'Links', hint: 'yaw −90°' },
  ]
  const [selected, setSelected] = useState<number | null>(null)
  return (
    <div className="w-screen h-screen flex flex-col items-center justify-center p-4">
      {selected == null ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-w-5xl">
          {views.map(v => (
            <button key={v.idx} onClick={() => setSelected(v.idx)}
              className="group relative rounded-2xl overflow-hidden bg-zinc-800">
              <img src={`/api/v1/photos/${photoId}/reframe/${v.idx}`}
                className="w-full aspect-video object-cover" />
              <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 to-transparent">
                <div className="text-white text-sm font-semibold">{v.label}</div>
                <div className="text-white/60 text-[10px]">{v.hint}</div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center gap-3">
          <img src={`/api/v1/photos/${photoId}/reframe/${selected}`}
            className="max-h-[85vh] max-w-full object-contain rounded-xl" />
          <button onClick={() => setSelected(null)}
            className="px-4 py-2 rounded-lg bg-white text-black text-sm font-semibold hover:bg-zinc-200">
            ← Zurück zu den Perspektiven
          </button>
        </div>
      )}
    </div>
  )
}

function DroneInfoOverlay({ photo }: { photo: Photo }) {
  const m = photo.drone_metadata
  if (!m) return null
  return (
    <div className="absolute bottom-4 left-4 right-4 sm:right-auto sm:max-w-md bg-black/70 text-white rounded-2xl p-4 backdrop-blur">
      <div className="flex items-center gap-2 mb-2">
        <Plane size={16} />
        <span className="font-semibold text-sm">Drohnen-Aufnahme</span>
      </div>
      {m.story && (
        <p className="text-sm mb-2 leading-relaxed">{m.story}</p>
      )}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        {m.relative_altitude_m != null && (
          <div><span className="text-white/60">Höhe (rel.)</span><br />{Math.round(m.relative_altitude_m)} m</div>
        )}
        {m.absolute_altitude_m != null && (
          <div><span className="text-white/60">Höhe (GPS)</span><br />{Math.round(m.absolute_altitude_m)} m</div>
        )}
        {m.gimbal_pitch != null && (
          <div><span className="text-white/60">Gimbal</span><br />{m.gimbal_pitch.toFixed(0)}°</div>
        )}
        {(m.make || m.model) && (
          <div className="col-span-2"><span className="text-white/60">Gerät</span><br />{[m.make, m.model].filter(Boolean).join(' ')}</div>
        )}
      </div>
    </div>
  )
}

// ── Three.js 360° Photo Viewer ─────────────────────────────────────────────
function SphereViewer({ imageUrl }: { imageUrl: string }) {
  const canvasRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const container = canvasRef.current
    if (!container) return
    const w = container.clientWidth
    const h = container.clientHeight

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(75, w / h, 0.1, 1000)
    camera.position.set(0, 0, 0.01)

    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(w, h)
    renderer.setPixelRatio(window.devicePixelRatio)
    container.appendChild(renderer.domElement)

    // Kugel mit invertierten Normalen — Textur wird von innen gesehen.
    const geometry = new THREE.SphereGeometry(50, 128, 64)
    geometry.scale(-1, 1, 1)

    const loader = new THREE.TextureLoader()
    loader.setCrossOrigin('anonymous')
    let mesh: THREE.Mesh | null = null
    loader.load(imageUrl, (tex: any) => {
      tex.colorSpace = THREE.SRGBColorSpace
      const material = new THREE.MeshBasicMaterial({ map: tex })
      mesh = new THREE.Mesh(geometry, material)
      scene.add(mesh)
    })

    // Simple orbit controls (Maus zum Schwenken, Scroll für Zoom/FOV)
    let lon = 0, lat = 0
    let dragging = false, dragX = 0, dragY = 0, startLon = 0, startLat = 0
    const onDown = (e: PointerEvent) => {
      dragging = true; dragX = e.clientX; dragY = e.clientY
      startLon = lon; startLat = lat
      container.setPointerCapture(e.pointerId)
    }
    const onMove = (e: PointerEvent) => {
      if (!dragging) return
      lon = startLon - (e.clientX - dragX) * 0.15
      lat = Math.max(-85, Math.min(85, startLat + (e.clientY - dragY) * 0.15))
    }
    const onUp = (e: PointerEvent) => {
      dragging = false
      try { container.releasePointerCapture(e.pointerId) } catch {}
    }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      camera.fov = Math.max(30, Math.min(110, camera.fov + e.deltaY * 0.05))
      camera.updateProjectionMatrix()
    }
    container.addEventListener('pointerdown', onDown)
    container.addEventListener('pointermove', onMove)
    container.addEventListener('pointerup', onUp)
    container.addEventListener('wheel', onWheel, { passive: false })

    let raf = 0
    const animate = () => {
      const phi = THREE.MathUtils.degToRad(90 - lat)
      const theta = THREE.MathUtils.degToRad(lon)
      camera.lookAt(
        500 * Math.sin(phi) * Math.cos(theta),
        500 * Math.cos(phi),
        500 * Math.sin(phi) * Math.sin(theta),
      )
      renderer.render(scene, camera)
      raf = requestAnimationFrame(animate)
    }
    animate()

    const onResize = () => {
      if (!container) return
      const w2 = container.clientWidth, h2 = container.clientHeight
      renderer.setSize(w2, h2)
      camera.aspect = w2 / h2
      camera.updateProjectionMatrix()
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
      container.removeEventListener('pointerdown', onDown)
      container.removeEventListener('pointermove', onMove)
      container.removeEventListener('pointerup', onUp)
      container.removeEventListener('wheel', onWheel as any)
      if (mesh) scene.remove(mesh)
      geometry.dispose()
      renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [imageUrl])
  return (
    <div className="relative w-full h-full">
      <div ref={canvasRef} className="w-screen h-screen cursor-grab active:cursor-grabbing" />
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/50 text-white text-xs px-3 py-1.5 rounded-full flex items-center gap-2 pointer-events-none">
        <Info size={12} /> Ziehen zum Schwenken · Scrollen zoomt
      </div>
    </div>
  )
}

function SphereVideoViewer({ videoUrl }: { videoUrl: string }) {
  const canvasRef = useRef<HTMLDivElement | null>(null)
  const vidRef = useRef<HTMLVideoElement | null>(null)
  useEffect(() => {
    const container = canvasRef.current
    if (!container) return
    const w = container.clientWidth, h = container.clientHeight

    const video = document.createElement('video')
    video.src = videoUrl
    video.crossOrigin = 'anonymous'
    video.loop = true
    video.muted = false
    video.playsInline = true
    video.play().catch(() => {})
    vidRef.current = video

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(75, w / h, 0.1, 1000)
    camera.position.set(0, 0, 0.01)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setSize(w, h)
    container.appendChild(renderer.domElement)

    const texture = new THREE.VideoTexture(video)
    texture.colorSpace = THREE.SRGBColorSpace
    const geometry = new THREE.SphereGeometry(50, 128, 64)
    geometry.scale(-1, 1, 1)
    const material = new THREE.MeshBasicMaterial({ map: texture })
    const mesh = new THREE.Mesh(geometry, material)
    scene.add(mesh)

    let lon = 0, lat = 0
    let dragging = false, dragX = 0, dragY = 0, startLon = 0, startLat = 0
    const onDown = (e: PointerEvent) => { dragging = true; dragX = e.clientX; dragY = e.clientY; startLon = lon; startLat = lat; container.setPointerCapture(e.pointerId) }
    const onMove = (e: PointerEvent) => { if (!dragging) return; lon = startLon - (e.clientX - dragX) * 0.15; lat = Math.max(-85, Math.min(85, startLat + (e.clientY - dragY) * 0.15)) }
    const onUp = (e: PointerEvent) => { dragging = false; try { container.releasePointerCapture(e.pointerId) } catch {} }
    container.addEventListener('pointerdown', onDown)
    container.addEventListener('pointermove', onMove)
    container.addEventListener('pointerup', onUp)

    let raf = 0
    const animate = () => {
      const phi = THREE.MathUtils.degToRad(90 - lat)
      const theta = THREE.MathUtils.degToRad(lon)
      camera.lookAt(500 * Math.sin(phi) * Math.cos(theta), 500 * Math.cos(phi), 500 * Math.sin(phi) * Math.sin(theta))
      renderer.render(scene, camera)
      raf = requestAnimationFrame(animate)
    }
    animate()
    return () => {
      cancelAnimationFrame(raf)
      video.pause()
      video.remove()
      container.removeEventListener('pointerdown', onDown)
      container.removeEventListener('pointermove', onMove)
      container.removeEventListener('pointerup', onUp)
      geometry.dispose(); renderer.dispose()
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement)
    }
  }, [videoUrl])
  return (
    <div className="relative w-full h-full">
      <div ref={canvasRef} className="w-screen h-screen cursor-grab active:cursor-grabbing" />
    </div>
  )
}
