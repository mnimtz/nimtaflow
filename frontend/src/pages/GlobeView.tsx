import { useEffect, useRef, useState } from 'react'
import Globe from 'react-globe.gl'

export interface GlobePoint { lat: number; lng: number; label: string; id: number }

/** 3D globe of photo locations. Lazy-loaded from MapPage so the heavy three.js
 * bundle only loads when the user switches to the globe. */
export default function GlobeView({ points, onPoint }: {
  points: GlobePoint[]; onPoint?: (id: number) => void
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const globeRef = useRef<any>(null)
  const [size, setSize] = useState({ w: 800, h: 600 })

  useEffect(() => {
    if (!wrap.current) return
    const ro = new ResizeObserver(entries => {
      const r = entries[0].contentRect
      setSize({ w: Math.floor(r.width), h: Math.floor(r.height) })
    })
    ro.observe(wrap.current)
    return () => ro.disconnect()
  }, [])

  // Allow zooming much closer (globe radius is 100; default minDistance is far).
  const tuneControls = () => {
    const g = globeRef.current
    if (!g) return
    const c = g.controls()
    c.enableZoom = true
    c.minDistance = 100.4    // right down onto the surface (street-level feel)
    c.maxDistance = 600
    c.zoomSpeed = 2.0
    c.enableDamping = true
    c.dampingFactor = 0.15
    c.autoRotate = false
  }

  // Click a location → smoothly fly the camera down to it (then notify parent).
  const flyTo = (p: GlobePoint) => {
    const g = globeRef.current
    if (g) g.pointOfView({ lat: p.lat, lng: p.lng, altitude: 0.04 }, 1200)
    onPoint?.(p.id)
  }

  return (
    <div ref={wrap} className="absolute inset-0 bg-[#0b1020]">
      <Globe
        ref={globeRef}
        onGlobeReady={tuneControls}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        pointsData={points}
        pointLat="lat"
        pointLng="lng"
        pointLabel="label"
        pointColor={() => '#818cf8'}
        pointAltitude={0.01}
        pointRadius={0.5}
        pointsMerge={false}
        onPointClick={(p: any) => flyTo(p as GlobePoint)}
        atmosphereColor="#6366f1"
        atmosphereAltitude={0.18}
      />
    </div>
  )
}
