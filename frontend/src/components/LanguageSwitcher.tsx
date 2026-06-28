import { useT, type Lang } from '../i18n'
import clsx from 'clsx'

const LANGS: { code: Lang; label: string }[] = [
  { code: 'de', label: 'DE' },
  { code: 'en', label: 'EN' },
]

/** Compact DE/EN segmented toggle. */
export default function LanguageSwitcher({ className }: { className?: string }) {
  const { lang, setLang } = useT()
  return (
    <div className={clsx('inline-flex rounded-lg overflow-hidden border border-white/10', className)}>
      {LANGS.map(({ code, label }) => (
        <button
          key={code}
          onClick={() => setLang(code)}
          className={clsx(
            'px-2.5 py-1 text-xs font-semibold transition-colors',
            lang === code
              ? 'bg-indigo-600 text-white'
              : 'bg-transparent text-zinc-400 hover:text-white hover:bg-white/5',
          )}
          aria-pressed={lang === code}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
