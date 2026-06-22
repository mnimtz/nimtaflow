import { useState } from 'react'
import { api, syncAuthCookie } from '../lib/api'

/** First-run setup: register the initial admin (shown when the server reports
 * needs_setup, i.e. a fresh install with no users). */
export default function SetupPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (pw !== pw2) { setError('Die Passwörter stimmen nicht überein.'); return }
    if (pw.length < 6) { setError('Passwort zu kurz (min. 6 Zeichen).'); return }
    setBusy(true)
    try {
      const res = await api.post('/auth/setup', { email, name, password: pw })
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      syncAuthCookie()
      window.location.href = '/'   // full reload → App re-checks status, enters app
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Einrichtung fehlgeschlagen.')
      setBusy(false)
    }
  }

  const inp = 'w-full px-3 py-2 rounded-lg bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-700 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <img src="/photoflow-logo.png" alt="NimtaFlow" className="h-16 w-auto object-contain mx-auto mb-3" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Willkommen 👋</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Lege dein Administrator-Konto an.</p>
        </div>
        <form onSubmit={submit} className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-800 p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
            <input className={inp} value={name} onChange={e => setName(e.target.value)} placeholder="Dein Name" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">E-Mail (= Login)</label>
            <input className={inp} type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Passwort (min. 6 Zeichen)</label>
            <input className={inp} type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="new-password" required />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Passwort wiederholen</label>
            <input className={inp} type="password" value={pw2} onChange={e => setPw2(e.target.value)} autoComplete="new-password" required />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          <button type="submit" disabled={busy || !email || !pw}
            className="w-full py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            {busy ? 'Erstelle Konto…' : 'Konto erstellen & loslegen'}
          </button>
        </form>
      </div>
    </div>
  )
}
