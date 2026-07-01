import { useState, useRef, useEffect, type ReactNode } from 'react'
import { RowsPhotoAlbum, MasonryPhotoAlbum } from 'react-photo-album'
import 'react-photo-album/rows.css'
import 'react-photo-album/masonry.css'
import { Heart, Play, Star, Check } from 'lucide-react'
import { thumbUrl, type Photo } from '../../lib/api'
import { groupByDate, type Indexed } from './justified'
import { useT } from '../../i18n'

export type LayoutMode = 'rows' | 'masonry'

// ── Sektions-Virtualisierung (à la Immich/Google Photos) ──────────────────────
// Nur Sektionen im (erweiterten) Sichtbereich sind echt im DOM; alles andere ist
// ein leeres Div bekannter Höhe. So bleiben DOM- UND JS-Kosten (react-photo-album
// Layout, React-Reconciliation) konstant, egal wie tief man scrollt — statt O(n)
// pro nachgeladener Seite. Gemessene Höhen werden gecacht, damit der Platzhalter
// exakt so hoch ist wie die gerenderte Sektion → kein Scroll-Springen.
const heightCache = new Map<string, number>()

function LazySection({ id, estHeight, scrollRoot, eager, children }: {
  id: string; estHeight: number; scrollRoot?: HTMLElement | null; eager?: boolean; children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(!!eager)
  const [h, setH] = useState(() => heightCache.get(id) ?? estHeight)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), {
      root: scrollRoot ?? null, rootMargin: '1400px 0px',
    })
    io.observe(el)
    return () => io.disconnect()
  }, [scrollRoot])

  // Solange sichtbar: echte Höhe messen und cachen → korrekter Platzhalter beim
  // späteren Aushängen, kein Scroll-Sprung.
  useEffect(() => {
    if (!visible || !ref.current) return
    const el = ref.current
    const measure = () => {
      const height = el.getBoundingClientRect().height
      if (height > 0) { heightCache.set(id, height); setH(height) }
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [visible, id])

  return <div ref={ref} style={visible ? undefined : { height: h }}>{visible ? children : null}</div>
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

type AlbumPhoto = { src: string; width: number; height: number; key: string; srcSet: { src: string; width: number; height: number }[]; _p: Photo; _i: number }

function toAlbum(items: Indexed[]): AlbumPhoto[] {
  return items.map(({ photo, index }) => {
    const w = photo.width || 1000, h = photo.height || 750
    const aspect = w / h
    // Responsive sources so big tiles load the sharp 1920px render, small tiles
    // the 320/800px ones — fixes blur from upscaling a single medium thumbnail.
    const srcSet = ([320, 800, 1920] as const).map(sw => ({
      src: thumbUrl(photo, sw === 320 ? 'small' : sw === 800 ? 'medium' : 'large'),
      width: sw, height: Math.round(sw / aspect),
    }))
    return { src: thumbUrl(photo, 'medium'), width: w, height: h, key: String(photo.id), srcSet, _p: photo, _i: index }
  })
}

function Overlay({ photo, index, selectable, isSel, onFav, onToggle }: {
  photo: Photo; index: number; selectable?: boolean; isSel: boolean
  onFav?: (p: Photo) => void; onToggle?: (p: Photo, i: number, shift: boolean) => void
}) {
  const { t } = useT()
  return (
    <>
      {photo.is_video && (
        <img src={`/api/photos/${photo.id}/preview`} alt="" draggable={false}
          className="pf-show absolute inset-0 w-full h-full object-cover pointer-events-none"
          loading="lazy" onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
      )}
      <div className={`absolute inset-x-0 top-0 h-14 bg-gradient-to-b from-black/40 to-transparent pointer-events-none ${isSel ? '' : 'pf-show'}`} />
      {selectable && (
        <button onClick={e => { e.stopPropagation(); onToggle?.(photo, index, (e as any).shiftKey) }} title={t('gallery.select')}
          className={`absolute top-2 left-2 w-6 h-6 rounded-full flex items-center justify-center z-10 ${isSel ? 'bg-indigo-500 text-white' : 'bg-black/35 text-white/90 pf-show hover:bg-black/55'}`}>
          <Check size={15} strokeWidth={3} />
        </button>
      )}
      {photo.is_video && (
        <div className="absolute bottom-2 left-2 bg-black/60 rounded px-1.5 py-0.5 flex items-center gap-1 pointer-events-none z-10">
          <Play size={10} fill="white" className="text-white" />
          {photo.duration_seconds != null && (
            <span className="text-white text-[10px] font-medium">{Math.floor(photo.duration_seconds / 60)}:{String(Math.floor(photo.duration_seconds % 60)).padStart(2, '0')}</span>
          )}
        </div>
      )}
      <button onClick={e => { e.stopPropagation(); onFav?.(photo) }}
        className={`absolute top-2 right-2 p-1 rounded-full z-10 ${photo.is_favorite ? 'bg-red-500 text-white' : 'bg-black/40 text-white pf-show'}`}>
        <Heart size={12} fill={photo.is_favorite ? 'white' : 'none'} />
      </button>
      {!!photo.user_rating && photo.user_rating > 0 && (
        <div className="absolute bottom-2 right-2 flex gap-0.5 pointer-events-none z-10">
          {Array.from({ length: photo.user_rating }).map((_, i) => <Star key={i} size={8} fill="gold" className="text-yellow-400" />)}
        </div>
      )}
    </>
  )
}

interface Props {
  photos: Photo[]
  layout?: LayoutMode
  rowHeight?: number
  groupBy?: 'none' | 'day' | 'month'
  scrollRoot?: HTMLElement | null
  onPhotoClick: (index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
  selectable?: boolean
  selected?: Set<number>
  onToggleSelect?: (photo: Photo, index: number, shift: boolean) => void
  onSelectMany?: (ids: number[], on: boolean) => void
}

function Album({ items, layout, rowHeight, anySelected, ...cb }: {
  items: Indexed[]; layout: LayoutMode; rowHeight: number; anySelected: boolean
} & Omit<Props, 'photos' | 'layout' | 'rowHeight' | 'groupBy' | 'scrollRoot'>) {
  const album = toAlbum(items)
  const common = {
    photos: album,
    spacing: 5,
    onClick: ({ photo, event }: any) => {
      const p = (photo as AlbumPhoto)._p, i = (photo as AlbumPhoto)._i
      if (cb.selectable && anySelected) cb.onToggleSelect?.(p, i, (event as any)?.shiftKey)
      else cb.onPhotoClick(i)
    },
    render: {
      // Face-aware crop: bias object-position to the face centre so heads aren't
      // cut off. Falls back to an upper-third bias (heads are usually up top).
      image: (props: any, ctx: any) => {
        const p = (ctx.photo as AlbumPhoto)._p
        const pos = (p.focus_x != null && p.focus_y != null)
          ? `${Math.round(p.focus_x * 100)}% ${Math.round(p.focus_y * 100)}%`
          : '50% 38%'
        return <img {...props} style={{ ...(props.style || {}), display: 'block', width: '100%', height: '100%', objectFit: 'cover', objectPosition: pos }} />
      },
      extras: (_: any, ctx: any) => {
        const p = (ctx.photo as AlbumPhoto)._p, i = (ctx.photo as AlbumPhoto)._i
        return <Overlay photo={p} index={i} selectable={cb.selectable} isSel={cb.selected?.has(p.id) ?? false} onFav={cb.onFavoriteToggle} onToggle={cb.onToggleSelect} />
      },
    },
  }
  if (layout === 'masonry') {
    return <MasonryPhotoAlbum {...common as any} columns={(w: number) => Math.max(2, Math.round(w / (rowHeight * 1.25)))} />
  }
  return <RowsPhotoAlbum {...common as any} targetRowHeight={rowHeight} rowConstraints={{ singleRowMaxHeight: Math.round(rowHeight * 1.35) }} />
}

export default function Gallery({ photos, layout = 'rows', rowHeight = 200, groupBy = 'none', scrollRoot, ...cb }: Props) {
  const { t } = useT()
  const anySelected = (cb.selected?.size ?? 0) > 0
  // Grobe Höhenschätzung pro Sektion (~5 Bilder/Reihe), bis die echte Höhe gemessen
  // und gecacht ist. Nur für den Platzhalter vor dem ersten Rendern relevant.
  const estRows = (n: number) => Math.ceil(n / 5) * (rowHeight + 5)

  if (groupBy === 'none') {
    // Flache Liste in feste Blöcke schneiden und jeden virtualisieren.
    const CH = 48
    const items = photos.map((photo, index) => ({ photo, index }))
    return (
      <div className="space-y-1">
        {chunk(items, CH).map((block, bi) => (
          <LazySection key={block[0]?.photo.id ?? bi} id={`flat:${block[0]?.photo.id ?? bi}`}
            estHeight={estRows(block.length)} scrollRoot={scrollRoot} eager={bi === 0}>
            <Album items={block} layout={layout} rowHeight={rowHeight} anySelected={anySelected} {...cb} />
          </LazySection>
        ))}
      </div>
    )
  }
  return (
    <div className="space-y-6">
      {groupByDate(photos, groupBy).map((g, gi) => {
        const ids = g.items.map(it => it.photo.id)
        const allSel = cb.selectable && ids.length > 0 && ids.every(id => cb.selected?.has(id))
        return (
          <LazySection key={g.key} id={`${groupBy}:${g.key}`} estHeight={estRows(g.items.length) + 44} scrollRoot={scrollRoot} eager={gi < 2}>
            <section data-gkey={g.key}>
              <div className="sticky top-0 z-20 py-2 mb-2 bg-gradient-to-b from-white via-white/95 to-white/0 dark:from-zinc-950 dark:via-zinc-950/95 dark:to-transparent backdrop-blur-sm flex items-baseline gap-2">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 capitalize">{g.label}</h3>
                <span className="text-xs text-zinc-400">{g.items.length}</span>
                {cb.selectable && (
                  <button onClick={() => cb.onSelectMany?.(ids, !allSel)}
                    className="ml-1 text-xs text-indigo-500 hover:text-indigo-400 font-medium">
                    {allSel ? t('gallery.deselect') : t('gallery.selectAll')}
                  </button>
                )}
              </div>
              <Album items={g.items} layout={layout} rowHeight={rowHeight} anySelected={anySelected} {...cb} />
            </section>
          </LazySection>
        )
      })}
    </div>
  )
}
