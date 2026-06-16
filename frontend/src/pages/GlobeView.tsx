import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

export interface GlobePoint { lat: number; lng: number; label: string; id: number }

/** Real zoomable 3D globe (MapLibre GL globe projection) built from actual OSM
 * map tiles — so you can spin the planet AND zoom seamlessly down to the exact
 * street-level location of a photo. Free, no API key. Lazy-loaded from MapPage. */
export default function GlobeView({ points, onPoint }: {
  points: GlobePoint[]; onPoint?: (id: number) => void
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

  useEffect(() => {
    if (!wrap.current || mapRef.current) return
    // Hi-DPI raster OSM — free, no token. (Swap for a satellite raster later.)
    const style: any = {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                  'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                  'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap',
        },
      },
      layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
    }
    const map = new maplibregl.Map({
      container: wrap.current,
      style,
      center: [10, 50],
      zoom: 1.4,
      attributionControl: false,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }))

    map.on('style.load', () => {
      map.setProjection({ type: 'globe' } as any)  // ← the real 3D globe
      map.setSky({ 'sky-color': '#0b1020', 'horizon-color': '#1a2348', 'fog-color': '#0b1020', 'fog-ground-blend': 0.4 } as any)

      const fc: any = {
        type: 'FeatureCollection',
        features: points.map(p => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
          properties: { id: p.id, label: p.label },
        })),
      }
      map.addSource('photos', { type: 'geojson', data: fc, cluster: true, clusterRadius: 45, clusterMaxZoom: 12 } as any)
      map.addLayer({
        id: 'clusters', type: 'circle', source: 'photos', filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#6366f1', 'circle-opacity': 0.85,
          'circle-radius': ['step', ['get', 'point_count'], 16, 10, 22, 50, 30],
          'circle-stroke-width': 2, 'circle-stroke-color': '#c7d2fe',
        },
      } as any)
      map.addLayer({
        id: 'cluster-count', type: 'symbol', source: 'photos', filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12 },
        paint: { 'text-color': '#fff' },
      } as any)
      map.addLayer({
        id: 'point', type: 'circle', source: 'photos', filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': '#818cf8', 'circle-radius': 7,
          'circle-stroke-width': 2, 'circle-stroke-color': '#fff',
        },
      } as any)

      // Click a cluster → zoom into it; click a photo → fly down + notify parent.
      map.on('click', 'clusters', (e) => {
        const f = map.queryRenderedFeatures(e.point, { layers: ['clusters'] })[0] as any
        const src = map.getSource('photos') as maplibregl.GeoJSONSource
        src.getClusterExpansionZoom(f.properties.cluster_id).then((z) => {
          map.easeTo({ center: (f.geometry as any).coordinates, zoom: z })
        }).catch(() => {})
      })
      map.on('click', 'point', (e) => {
        const f = e.features?.[0] as any
        if (!f) return
        map.flyTo({ center: f.geometry.coordinates, zoom: 15, speed: 1.2 })
        onPoint?.(f.properties.id)
      })
      for (const id of ['clusters', 'point']) {
        map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', id, () => { map.getCanvas().style.cursor = '' })
      }
    })

    const ro = new ResizeObserver(() => map.resize())
    ro.observe(wrap.current)
    return () => { ro.disconnect(); map.remove(); mapRef.current = null }
  }, [])

  // Update points if they change after mount.
  useEffect(() => {
    const map = mapRef.current
    const src = map?.getSource('photos') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    src.setData({
      type: 'FeatureCollection',
      features: points.map(p => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
        properties: { id: p.id, label: p.label },
      })),
    } as any)
  }, [points])

  return <div ref={wrap} className="absolute inset-0" />
}
