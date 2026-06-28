import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X, AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react'

/* ───────────────────────── Modal ─────────────────────────
 * Themed, portal-based modal. Closes on backdrop click + Esc.
 * Replaces the ad-hoc `fixed inset-0` blocks scattered around.
 */
export function Modal({
  open,
  onClose,
  title,
  children,
  maxWidth = 'max-w-md',
}: {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  maxWidth?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-[fadeIn_120ms_ease-out]"
      onClick={onClose}
    >
      <div
        className={`w-full ${maxWidth} max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl`}
        onClick={e => e.stopPropagation()}
      >
        {title !== undefined && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
            <h2 className="text-base font-semibold text-zinc-900 dark:text-white">{title}</h2>
            <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors">
              <X size={18} />
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

/* ───────────────────────── Toasts ───────────────────────── */
type ToastKind = 'success' | 'error' | 'info'
interface Toast { id: number; kind: ToastKind; message: string }

/* ───────────────────────── Confirm ───────────────────────── */
interface ConfirmOpts {
  title: string
  message?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}
interface PendingConfirm extends ConfirmOpts { id: number; resolve: (v: boolean) => void }

interface DialogsCtx {
  toast: (message: string, kind?: ToastKind) => void
  confirm: (opts: ConfirmOpts) => Promise<boolean>
}
const Ctx = createContext<DialogsCtx | null>(null)

export function useToast() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useToast must be used within DialogsProvider')
  return c.toast
}
export function useConfirm() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useConfirm must be used within DialogsProvider')
  return c.confirm
}

let _id = 1

export function DialogsProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [confirms, setConfirms] = useState<PendingConfirm[]>([])

  const toast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = _id++
    setToasts(t => [...t, { id, kind, message }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000)
  }, [])

  const confirm = useCallback((opts: ConfirmOpts) => {
    return new Promise<boolean>(resolve => {
      const id = _id++
      setConfirms(c => [...c, { ...opts, id, resolve }])
    })
  }, [])

  const closeConfirm = (id: number, value: boolean) => {
    setConfirms(cs => {
      const found = cs.find(c => c.id === id)
      found?.resolve(value)
      return cs.filter(c => c.id !== id)
    })
  }

  const Icon = { success: CheckCircle2, error: XCircle, info: Info }
  const color = { success: 'text-emerald-400', error: 'text-red-400', info: 'text-indigo-400' }

  return (
    <Ctx.Provider value={{ toast, confirm }}>
      {children}

      {/* toasts */}
      {createPortal(
        <div className="fixed top-4 right-4 z-[200] flex flex-col gap-2 pointer-events-none">
          {toasts.map(t => {
            const I = Icon[t.kind]
            return (
              <div key={t.id}
                className="pointer-events-auto flex items-center gap-2.5 px-4 py-3 rounded-xl bg-zinc-900/95 border border-zinc-700 shadow-2xl text-sm text-zinc-100 min-w-[240px] max-w-sm animate-[slideIn_160ms_ease-out]">
                <I size={17} className={color[t.kind]} />
                <span className="flex-1">{t.message}</span>
              </div>
            )
          })}
        </div>,
        document.body,
      )}

      {/* confirms */}
      {confirms.map(c => (
        <Modal key={c.id} open onClose={() => closeConfirm(c.id, false)} maxWidth="max-w-sm">
          <div className="flex gap-3">
            {c.danger && <AlertTriangle size={22} className="text-red-400 flex-shrink-0 mt-0.5" />}
            <div className="flex-1">
              <h3 className="text-base font-semibold text-zinc-900 dark:text-white mb-1">{c.title}</h3>
              {c.message && <div className="text-sm text-zinc-600 dark:text-zinc-400">{c.message}</div>}
            </div>
          </div>
          <div className="flex gap-2 justify-end mt-5">
            <button onClick={() => closeConfirm(c.id, false)}
              className="px-3.5 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
              {c.cancelLabel || 'Abbrechen'}
            </button>
            <button onClick={() => closeConfirm(c.id, true)}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium text-white ${c.danger ? 'bg-red-600 hover:bg-red-500' : 'bg-indigo-600 hover:bg-indigo-500'}`}>
              {c.confirmLabel || 'OK'}
            </button>
          </div>
        </Modal>
      ))}
    </Ctx.Provider>
  )
}
