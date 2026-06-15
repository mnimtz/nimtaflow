import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Fullscreen from 'yet-another-react-lightbox/plugins/fullscreen'
import Slideshow from 'yet-another-react-lightbox/plugins/slideshow'
import Thumbnails from 'yet-another-react-lightbox/plugins/thumbnails'
import 'yet-another-react-lightbox/plugins/thumbnails.css'
import Counter from 'yet-another-react-lightbox/plugins/counter'
import 'yet-another-react-lightbox/plugins/counter.css'
import Captions from 'yet-another-react-lightbox/plugins/captions'
import 'yet-another-react-lightbox/plugins/captions.css'
import Video from 'yet-another-react-lightbox/plugins/video'
import { thumbUrl, type Photo } from '../../lib/api'

/** Modern lightbox: pinch/wheel zoom, fullscreen, slideshow, thumbnail strip,
 * counter, captions and inline video playback. */
export default function GalleryLightbox({ photos, index, onClose }: {
  photos: Photo[]; index: number; onClose: () => void
}) {
  const slides = photos.map(p => p.is_video
    ? {
        type: 'video' as const,
        poster: thumbUrl(p, 'large'),
        width: p.width || 1280, height: p.height || 720,
        sources: [{ src: `/api/photos/${p.id}/video/stream`, type: 'video/mp4' }],
        description: p.filename,
      }
    : {
        src: thumbUrl(p, 'large'),
        width: p.width || undefined, height: p.height || undefined,
        description: p.filename,
        download: `/api/photos/${p.id}/original`,
      })

  return (
    <Lightbox
      open index={index} close={onClose} slides={slides as any}
      plugins={[Zoom, Fullscreen, Slideshow, Thumbnails, Counter, Captions, Video]}
      zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
      thumbnails={{ position: 'bottom', width: 96, height: 64, border: 0, gap: 6 }}
      counter={{ container: { style: { top: 'unset', bottom: 0 } } }}
      captions={{ descriptionTextAlign: 'center' }}
      carousel={{ finite: false, preload: 2 }}
      styles={{ container: { backgroundColor: 'rgba(0,0,0,0.92)' } }}
      animation={{ fade: 250, swipe: 300 }}
    />
  )
}
