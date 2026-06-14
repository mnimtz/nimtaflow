import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Folder, FolderOpen, ChevronRight, ChevronUp, Check, X, HardDrive } from 'lucide-react'
import { api } from '../../lib/api'

type DirEntry = { name: string; path: string; has_children: boolean }
type DirListing = { path: string; parent: string | null; entries: DirEntry[] }

type Props = {
  onSelect: (path: string) => void
  onClose: () => void
  initialPath?: string
}

export default function FolderBrowser({ onSelect, onClose, initialPath = '/' }: Props) {
  const [currentPath, setCurrentPath] = useState(initialPath)

  const { data, isLoading, error } = useQuery<DirListing>({
    queryKey: ['fs-browse', currentPath],
    queryFn: () => api.get('/fs/browse', { params: { path: currentPath } }).then((r) => r.data),
  })

  const breadcrumbs = currentPath === '/'
    ? ['/']
    : ['/', ...currentPath.slice(1).split('/')]

  function navigateToCrumb(index: number) {
    if (index === 0) { setCurrentPath('/'); return }
    const parts = currentPath.slice(1).split('/')
    setCurrentPath('/' + parts.slice(0, index).join('/'))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg flex flex-col"
        style={{ maxHeight: '80vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <HardDrive size={16} className="text-gray-500" />
            <span className="text-sm font-semibold text-gray-900 dark:text-white">Ordner auswählen</span>
          </div>
          <button onClick={onClose} className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
            <X size={18} />
          </button>
        </div>

        {/* Breadcrumb */}
        <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800 flex items-center gap-1 flex-wrap">
          {breadcrumbs.map((crumb, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight size={12} className="text-gray-400" />}
              <button
                onClick={() => navigateToCrumb(i)}
                className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-mono"
              >
                {crumb}
              </button>
            </span>
          ))}
        </div>

        {/* Go up */}
        {data?.parent && (
          <button
            onClick={() => setCurrentPath(data.parent!)}
            className="flex items-center gap-2 px-4 py-2 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border-b border-gray-100 dark:border-gray-800"
          >
            <ChevronUp size={15} />
            <span className="font-mono">..</span>
          </button>
        )}

        {/* Directory list */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="flex justify-center py-8 text-gray-400 text-sm">Lade...</div>
          )}
          {error && (
            <div className="px-4 py-3 text-sm text-red-500">Zugriff verweigert oder Verzeichnis nicht gefunden.</div>
          )}
          {data?.entries.length === 0 && !isLoading && (
            <div className="px-4 py-8 text-center text-sm text-gray-400">Keine Unterordner</div>
          )}
          {data?.entries.map((entry) => (
            <button
              key={entry.path}
              onClick={() => entry.has_children ? setCurrentPath(entry.path) : undefined}
              onDoubleClick={() => setCurrentPath(entry.path)}
              className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
            >
              {entry.has_children
                ? <FolderOpen size={17} className="text-yellow-500 shrink-0" />
                : <Folder size={17} className="text-yellow-400 shrink-0" />
              }
              <span className="flex-1 font-mono text-gray-800 dark:text-gray-200 truncate">{entry.name}</span>
              {entry.has_children && (
                <ChevronRight size={14} className="text-gray-300 dark:text-gray-600 group-hover:text-gray-500 shrink-0" />
              )}
            </button>
          ))}
        </div>

        {/* Footer — current selection */}
        <div className="border-t border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center gap-3">
          <code className="flex-1 text-xs text-gray-500 dark:text-gray-400 font-mono truncate bg-gray-50 dark:bg-gray-800 px-2 py-1 rounded">
            {currentPath}
          </code>
          <button
            onClick={() => { onSelect(currentPath); onClose() }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shrink-0"
          >
            <Check size={14} />
            Auswählen
          </button>
        </div>
      </div>
    </div>
  )
}
