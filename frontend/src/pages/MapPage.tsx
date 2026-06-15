import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import { Layers, Navigation } from 'lucide-react'
import { api, Photo } from '../lib/api'
import 'leaflet/dist/leaflet.css'
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
  wiki: {
    label: 'Wikimedia',
    url: 'https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png',
    attribution: '&copy; Wikimedia',
  },
} as const
type LayerKey = keyof typeof LAYERS

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

  const { data, isLoading } = useQuery({
    queryKey: ['photos-map'],
    queryFn: () => api.get('/photos', { params: { has_gps: true, limit: 2000, page: 1 } }).then((r) => r.data.items as Photo[]),
  })

  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then((r) => r.data),
    staleTime: 60_000,
  })
  const streetView = (settings?.['map.streetview'] ?? 'true') !== 'false'

  useEffect(() => {
    const def = settings?.['map.default_layer'] as LayerKey | undefined
    if (def && def in LAYERS) setLayer(def)
  }, [settings])

  const withGps = useMemo(() => (data ?? []).filter((p) => p.latitude && p.longitude), [data])
  const points = useMemo(() => withGps.map((p) => [p.latitude!, p.longitude!] as [number, number]), [withGps])

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">Karte</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500 dark:text-gray-400">{withGps.length} Fotos mit GPS</span>
          <div className="flex items-center rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
            <Layers size={13} className="text-gray-400 ml-1.5 mr-0.5" />
            {(Object.keys(LAYERS) as LayerKey[]).map((k) => (
              <button
                key={k}
                onClick={() => setLayer(k)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  layer === k
                    ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
                }`}
              >
                {LAYERS[k].label}
              </button>
            ))}
          </div>
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
        ) : (
          <MapContainer center={[51.1657, 10.4515]} zoom={5} className="h-full w-full">
            <TileLayer key={layer} attribution={LAYERS[layer].attribution} url={LAYERS[layer].url} />
            <FitBounds points={points} />
            {withGps.map((photo) => (
              <Marker key={photo.id} position={[photo.latitude!, photo.longitude!]}>
                <Popup>
                  <div className="text-center">
                    <img
                      src={`/api/photos/${photo.id}/thumbnail?size=small`}
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
          </MapContainer>
        )}
      </div>
    </div>
  )
}
