import { useEffect, useRef, useState } from 'react'
import Globe from 'react-globe.gl'

export interface GlobePoint { lat: number; lng: number; label: string; id: number }

/** 3D globe of photo locations. Lazy-loaded from MapPage so the heavy three.js
 * bundle only loads when the user switches to the globe. */
export default function GlobeView({ points, onPoint }: {
  points: GlobePoint[]; onPoint?: (id: number) => void
}) {
  const wrap = useRef<HTMLDivElement>(null)
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

  return (
    <div ref={wrap} className="absolute inset-0 bg-[#0b1020]">
      <Globe
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
        pointAltitude={0.015}
        pointRadius={0.35}
        pointsMerge={false}
        onPointClick={(p: any) => onPoint?.(p.id)}
        atmosphereColor="#6366f1"
        atmosphereAltitude={0.18}
      />
    </div>
  )
}
