import { useState, useMemo, useEffect, Suspense, lazy } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import { Layers, Navigation, Globe2, Map as MapIcon } from 'lucide-react'
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

export default function MapPage() {
  const [layer, setLayer] = useState<LayerKey>('osm')
  const [view3d, setView3d] = useState(false)
  const [lbIndex, setLbIndex] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['photos-map'],
    queryFn: () => api.get('/photos/map').then((r) => r.data as Photo[]),
  })

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

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">Karte</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500 dark:text-gray-400">{withGps.length} Fotos mit GPS</span>
          <button
            onClick={() => setView3d(v => !v)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
            title={view3d ? 'Flache Karte' : '3D-Globus'}
          >
            {view3d ? <><MapIcon size={14} /> Karte</> : <><Globe2 size={14} /> Globus</>}
          </button>
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
