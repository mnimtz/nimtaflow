import { useEffect, useRef } from 'react'
import Masonry from 'react-masonry-css'
import { Photo } from '../../lib/api'

const BREAKPOINTS = {
  default: 6,
  1536: 5,
  1280: 4,
  1024: 3,
  768: 2,
  480: 2,
}

type Props = {
  photos: Photo[]
  onSelect: (p: Photo) => void
  onLoadMore: () => void
  hasMore?: boolean
  loadingMore?: boolean
}

export default function PhotoGrid({ photos, onSelect, onLoadMore, hasMore, loadingMore }: Props) {
  const sentinelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting && hasMore && !loadingMore) onLoadMore() },
      { rootMargin: '400px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasMore, loadingMore, onLoadMore])

  return (
    <>
      <Masonry
        breakpointCols={BREAKPOINTS}
        className="masonry-grid"
        columnClassName="masonry-grid_column"
      >
        {photos.map((photo) => (
          <PhotoTile key={photo.id} photo={photo} onClick={() => onSelect(photo)} />
        ))}
      </Masonry>
      <div ref={sentinelRef} className="h-8 flex items-center justify-center">
        {loadingMore && <span className="text-sm text-gray-400">Lade mehr…</span>}
      </div>
    </>
  )
}

function PhotoTile({ photo, onClick }: { photo: Photo; onClick: () => void }) {
  const src = photo.thumb_medium
    ? `/api/photos/${photo.id}/thumbnail?size=medium`
    : `/api/photos/${photo.id}/thumbnail?size=small`

  const aspectRatio = photo.width && photo.height ? photo.height / photo.width : 0.75

  return (
    <div
      onClick={onClick}
      className="relative overflow-hidden rounded cursor-pointer group bg-gray-100 dark:bg-gray-800"
      style={{ paddingBottom: `${aspectRatio * 100}%` }}
    >
      <img
        src={src}
        alt={photo.filename}
        loading="lazy"
        decoding="async"
        className="absolute inset-0 w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-200" />
    </div>
  )
}
