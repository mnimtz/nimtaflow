import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import { api, Photo } from '../lib/api'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

// Fix Leaflet default icon
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

export default function MapPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['photos-map'],
    queryFn: () => api.get('/photos', { params: { limit: 1000, page: 1 } }).then((r) => r.data.items as Photo[]),
  })

  const withGps = (data ?? []).filter((p) => p.latitude && p.longitude)

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">Karte</h1>
        <span className="text-sm text-gray-500 dark:text-gray-400">{withGps.length} Fotos mit GPS</span>
      </div>

      <div className="flex-1 relative">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center text-gray-400">Lade Karte…</div>
        ) : (
          <MapContainer
            center={[51.1657, 10.4515]}
            zoom={6}
            className="h-full w-full"
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {withGps.map((photo) => (
              <Marker key={photo.id} position={[photo.latitude!, photo.longitude!]}>
                <Popup>
                  <div className="text-center">
                    <img
                      src={`/api/photos/${photo.id}/thumbnail?size=small`}
                      alt={photo.filename}
                      className="w-32 h-32 object-cover rounded mb-1"
                    />
                    <p className="text-xs text-gray-600 truncate max-w-32">{photo.filename}</p>
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
