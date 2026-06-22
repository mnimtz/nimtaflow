import { useState, useMemo, useEffect, Suspense, lazy, Fragment } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, Polyline, CircleMarker, Tooltip, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import { Layers, Navigation, Globe2, Map as MapIcon, Route } from 'lucide-react'
import { api, Photo, thumbUrl } from '../lib/api'

const GlobeView = lazy(() => import('./GlobeView'))
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import 'leaflet/dist/leaflet.css'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import L from 'leaflet'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

// Key-free tile providers
const LAYERS = {
  osm: {
    label: 'Standard',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap',
  },
  satellite: {
    label: 'Satellit',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: '&copy; Esri',
  },
  dark: {
    label: 'Dunkel',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; CARTO',
  },
  topo: {
    label: 'Topo',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenTopoMap',
  },
  light: {
    label: 'Hell',
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; CARTO',
  },
  voyager: {
    label: 'Voyager',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attribution: '&copy; CARTO',
  },
  google: {
    label: 'Google',
    url: 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
    attribution: '&copy; Google',
  },
  google_sat: {
    label: 'Google Satellit',
    url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    attribution: '&copy; Google',
  },
  google_hybrid: {
    label: 'Google Hybrid',
    url: 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attribution: '&copy; Google',
  },
} as const
type LayerKey = string

type Waypoint = { place?: string; country?: string; date?: string; lat: number; lng: number }
type Trip = { id: number; name: string; route: Waypoint[] }
// Distinct, high-contrast colours cycled per trip route (cruise lines over sea etc.)
const ROUTE_COLORS = ['#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#a855f7', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#06b6d4']

/** Fit the map to all photo markers once they load. */
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 0) {
      map.fitBounds(points as any, { padding: [50, 50], maxZoom: 14 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points.length])
  return null
}

/** Fly to a searched place when the target changes. */
function FlyTo({ target }: { target: { lat: number; lng: number; seq: number } | null }) {
  const map = useMap()
  useEffect(() => {
    if (target) map.flyTo([target.lat, target.lng], 13, { duration: 1.2 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.seq])
  return null
}

export default function MapPage() {
  const [layer, setLayer] = useState<LayerKey>('osm')
  const [view3d, setView3d] = useState(false)
  const [lbIndex, setLbIndex] = useState<number | null>(null)
  const [showRoutes, setShowRoutes] = useState(false)
  const [showPlaces, setShowPlaces] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['photos-map'],
    queryFn: () => api.get('/photos/map').then((r) => r.data as Photo[]),
  })

  // Trip routes (cruise/ship lines etc.) — albums flagged as trips with >=2 waypoints.
  const { data: albums } = useQuery({
    queryKey: ['albums'],
    queryFn: () => api.get('/albums').then((r) => r.data as any[]),
    staleTime: 60_000,
  })
  const trips = useMemo<Trip[]>(() => (albums ?? [])
    .filter((a) => a.smart_criteria?.trip && Array.isArray(a.smart_criteria?.route))
    .map((a) => ({
      id: a.id, name: a.name,
      route: (a.smart_criteria.route as Waypoint[]).filter((w) => w.lat != null && w.lng != null),
    }))
    .filter((t) => t.route.length >= 2), [albums])

  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then((r) => r.data),
    staleTime: 60_000,
  })
  const streetView = (settings?.['map.streetview'] ?? 'true') !== 'false'

  // runtime layer set incl. optional MapTiler (needs API key)
  const mtKey = settings?.['map.maptiler_key']
  const layers: Record<string, { label: string; url: string; attribution: string }> = {
    ...LAYERS,
    ...(mtKey ? {
      maptiler: { label: 'MapTiler', url: `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=${mtKey}`, attribution: '&copy; MapTiler & OpenStreetMap' },
      maptiler_sat: { label: 'MapTiler Satellit', url: `https://api.maptiler.com/maps/satellite/{z}/{x}/{y}.jpg?key=${mtKey}`, attribution: '&copy; MapTiler' },
    } : {}),
  }

  useEffect(() => {
    const def = settings?.['map.default_layer']
    if (def && def in layers) setLayer(def)
  }, [settings])
  useEffect(() => {
    if ((settings?.['map.globe_default'] ?? 'false') === 'true') setView3d(true)
  }, [settings])

  const withGps = useMemo(() => (data ?? []).filter((p) => p.latitude && p.longitude), [data])
  const points = useMemo(() => withGps.map((p) => [p.latitude!, p.longitude!] as [number, number]), [withGps])

  // Distinct places from the user's OWN photo locations (no external geocoding) —
  // averaged coordinates + photo count, most photos first.
  const places = useMemo(() => {
    const m = new Map<string, { name: string; lat: number; lng: number; n: number }>()
    for (const p of withGps) {
      const name = ((p as any).city || (p as any).location_name || (p as any).country || '').trim()
      if (!name) continue
      const e = m.get(name) || { name, lat: 0, lng: 0, n: 0 }
      e.lat += p.latitude!; e.lng += p.longitude!; e.n++
      m.set(name, e)
    }
    return [...m.values()].map(e => ({ name: e.name, lat: e.lat / e.n, lng: e.lng / e.n, n: e.n }))
      .sort((a, b) => b.n - a.n)
  }, [withGps])
  const [placeQuery, setPlaceQuery] = useState('')
  const [flyTarget, setFlyTarget] = useState<{ lat: number; lng: number; seq: number } | null>(null)
  const placeMatches = useMemo(() =>
    placeQuery.trim() ? places.filter(p => p.name.toLowerCase().includes(placeQuery.toLowerCase())).slice(0, 30) : [],
    [places, placeQuery])

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">Karte</h1>
        <div className="flex items-center gap-3">
          {!view3d && places.length > 0 && (
            <button
              onClick={() => setShowPlaces(v => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border ${showPlaces
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/30'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
              title="Orte durchsuchen und anspringen"
            >
              <Navigation size={14} /> Orte ({places.length})
            </button>
          )}
          <span className="text-sm text-gray-500 dark:text-gray-400">{withGps.length} Fotos mit GPS</span>
          <button
            onClick={() => setView3d(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            title={view3d ? 'Flache Karte' : '3D-Globus'}
          >
            {view3d ? <><MapIcon size={14} /> Karte</> : <><Globe2 size={14} /> Globus</>}
          </button>
          {!view3d && trips.length > 0 && (
            <button
              onClick={() => setShowRoutes(v => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border ${showRoutes
                ? 'border-indigo-500 text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/30'
                : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
              title="Reise-/Seerouten ein-/ausblenden"
            >
              <Route size={14} /> Routen{showRoutes ? ` (${trips.length})` : ''}
            </button>
          )}
          {!view3d && (
            <div className="flex items-center gap-1.5">
              <Layers size={14} className="text-gray-400" />
              <select
                value={layer}
                onChange={(e) => setLayer(e.target.value)}
                className="px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {Object.keys(layers).map((k) => (
                  <option key={k} value={k}>{layers[k].label}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 relative">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400">Lade Karte…</div>
        ) : withGps.length === 0 ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center text-gray-400">
            <Navigation size={40} className="mb-3 opacity-40" />
            <p className="text-sm">Keine Fotos mit GPS-Daten gefunden.</p>
            <p className="text-xs mt-1 opacity-70">Fotos mit Geo-Koordinaten erscheinen hier automatisch.</p>
          </div>
        ) : view3d ? (
          <Suspense fallback={<div className="absolute inset-0 flex items-center justify-center text-gray-400 bg-[#0b1020]">Globus wird geladen…</div>}>
            <GlobeView
              points={withGps.map(p => ({ id: p.id, lat: p.latitude!, lng: p.longitude!, label: p.filename }))}
              onPoint={(id) => { const i = withGps.findIndex(p => p.id === id); if (i >= 0) setLbIndex(i) }}
            />
          </Suspense>
        ) : (
          <MapContainer center={[51.1657, 10.4515]} zoom={5} className="h-full w-full">
            <TileLayer key={layer} attribution={(layers[layer] ?? layers.osm).attribution} url={(layers[layer] ?? layers.osm).url} />
            <FitBounds points={points} />
            <FlyTo target={flyTarget} />
            {showRoutes && trips.map((trip, ti) => {
              const color = ROUTE_COLORS[ti % ROUTE_COLORS.length]
              const line = trip.route.map(w => [w.lat, w.lng] as [number, number])
              return (
                <Fragment key={trip.id}>
                  <Polyline positions={line} pathOptions={{ color, weight: 3, opacity: 0.85, dashArray: '6 6' }}>
                    <Tooltip sticky>{trip.name}</Tooltip>
                  </Polyline>
                  {trip.route.map((w, wi) => (
                    <CircleMarker key={wi} center={[w.lat, w.lng]} radius={5}
                      pathOptions={{ color, fillColor: color, fillOpacity: 1, weight: 2 }}>
                      <Tooltip>{[w.place, w.country].filter(Boolean).join(', ') || trip.name}</Tooltip>
                    </CircleMarker>
                  ))}
                </Fragment>
              )
            })}
            <MarkerClusterGroup chunkedLoading maxClusterRadius={50}>
            {withGps.map((photo) => (
              <Marker key={photo.id} position={[photo.latitude!, photo.longitude!]}>
                <Popup>
                  <div className="text-center">
                    <img
                      src={thumbUrl(photo, 'small')}
                      alt={photo.filename}
                      className="w-36 h-36 object-cover rounded mb-1.5"
                    />
                    <p className="text-xs text-gray-600 truncate max-w-[9rem]">{photo.filename}</p>
                    {streetView && (
                      <a
                        href={`https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${photo.latitude},${photo.longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block mt-1 text-[11px] text-indigo-600 hover:underline"
                      >
                        📍 In Street View öffnen
                      </a>
                    )}
                  </div>
                </Popup>
              </Marker>
            ))}
            </MarkerClusterGroup>
          </MapContainer>
        )}

        {/* Orts-Panel: durchblätterbare Liste aller Orte (Suche + Foto-Zahl, anklickbar) */}
        {!view3d && showPlaces && places.length > 0 && (
          <div className="absolute top-3 left-3 z-[1000] w-64 max-h-[calc(100%-1.5rem)] flex flex-col rounded-xl border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/95 backdrop-blur shadow-xl">
            <div className="p-2 border-b border-gray-200 dark:border-gray-800">
              <input
                autoFocus
                value={placeQuery}
                onChange={e => setPlaceQuery(e.target.value)}
                placeholder={`Ort suchen … (${places.length})`}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div className="overflow-auto">
              {(placeQuery.trim() ? placeMatches : places).map(pl => (
                <button key={pl.name}
                  onClick={() => setFlyTarget({ lat: pl.lat, lng: pl.lng, seq: Date.now() })}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-xs text-left text-gray-800 dark:text-gray-200 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 border-b border-gray-100 dark:border-gray-800/60">
                  <span className="truncate">{pl.name}</span>
                  <span className="text-gray-400 shrink-0">{pl.n}</span>
                </button>
              ))}
              {placeQuery.trim() && placeMatches.length === 0 && (
                <div className="px-3 py-3 text-xs text-gray-400">Keine Treffer</div>
              )}
            </div>
          </div>
        )}
      </div>

      {lbIndex != null && (
        <GalleryLightbox
          photos={withGps}
          index={lbIndex}
          onClose={() => setLbIndex(null)}
        />
      )}
    </div>
  )
}
