import { useRef, useState, useEffect } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize, RotateCcw } from 'lucide-react'

type Props = {
  photoId: number
  className?: string
  autoPlay?: boolean
}

function formatTime(s: number) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

export default function VideoPlayer({ photoId, className = '', autoPlay = false }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [showControls, setShowControls] = useState(true)
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (autoPlay) videoRef.current?.play()
  }, [autoPlay])

  function scheduleHide() {
    if (hideTimer.current) clearTimeout(hideTimer.current)
    setShowControls(true)
    hideTimer.current = setTimeout(() => setShowControls(false), 2500)
  }

  function togglePlay() {
    const v = videoRef.current
    if (!v) return
    if (v.paused) { v.play(); setPlaying(true) }
    else { v.pause(); setPlaying(false) }
    scheduleHide()
  }

  function handleTimeUpdate() {
    const v = videoRef.current
    if (!v) return
    setCurrentTime(v.currentTime)
    setProgress(v.duration ? (v.currentTime / v.duration) * 100 : 0)
  }

  function seek(e: React.MouseEvent<HTMLDivElement>) {
    const v = videoRef.current
    if (!v || !v.duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    v.currentTime = ratio * v.duration
    scheduleHide()
  }

  function toggleMute() {
    const v = videoRef.current
    if (!v) return
    v.muted = !v.muted
    setMuted(v.muted)
  }

  function fullscreen() {
    videoRef.current?.requestFullscreen?.()
  }

  return (
    <div
      className={`relative bg-black select-none ${className}`}
      onMouseMove={scheduleHide}
      onClick={togglePlay}
    >
      <video
        ref={videoRef}
        src={`/api/photos/${photoId}/video/stream`}
        className="w-full h-full object-contain"
        muted={muted}
        loop
        playsInline
        onLoadedMetadata={() => setDuration(videoRef.current?.duration || 0)}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />

      {/* Play overlay for stopped state */}
      {!playing && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="bg-black/50 rounded-full p-4">
            <Play size={36} fill="white" className="text-white" />
          </div>
        </div>
      )}

      {/* Controls bar */}
      <div
        className={`absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 transition-opacity duration-300 ${showControls ? 'opacity-100' : 'opacity-0'}`}
        onClick={e => e.stopPropagation()}
      >
        {/* Progress bar */}
        <div
          className="h-1 bg-white/30 rounded-full mb-3 cursor-pointer"
          onClick={seek}
        >
          <div
            className="h-full bg-white rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex items-center gap-3">
          <button onClick={togglePlay} className="text-white hover:text-gray-300 transition-colors">
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <span className="text-white text-xs font-mono">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <div className="flex-1" />
          <button onClick={toggleMute} className="text-white hover:text-gray-300 transition-colors">
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <button
            onClick={() => { if (videoRef.current) videoRef.current.currentTime = 0 }}
            className="text-white hover:text-gray-300 transition-colors"
          >
            <RotateCcw size={14} />
          </button>
          <button onClick={fullscreen} className="text-white hover:text-gray-300 transition-colors">
            <Maximize size={15} />
          </button>
        </div>
      </div>
    </div>
  )
}
