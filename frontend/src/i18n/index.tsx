import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { de } from './de'
import { en } from './en'

export type Lang = 'de' | 'en'

const DICTS: Record<Lang, Record<string, string>> = { de, en }

function detectLang(): Lang {
  try {
    const stored = localStorage.getItem('lang')
    if (stored === 'de' || stored === 'en') return stored
  } catch {
    /* ignore */
  }
  const navLangs =
    (typeof navigator !== 'undefined' &&
      (navigator.languages?.length ? navigator.languages : [navigator.language])) ||
    []
  for (const l of navLangs) {
    if (l && l.toLowerCase().startsWith('de')) return 'de'
    if (l && l.toLowerCase().startsWith('en')) return 'en'
  }
  return 'de'
}

type TFunc = (key: string, vars?: Record<string, string | number>) => string

interface I18nValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: TFunc
}

const I18nContext = createContext<I18nValue | null>(null)

function interpolate(s: string, vars?: Record<string, string | number>): string {
  if (!vars) return s
  return s.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`))
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectLang)

  useEffect(() => {
    try {
      document.documentElement.lang = lang
    } catch {
      /* ignore */
    }
  }, [lang])

  const setLang = (l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('lang', l)
    } catch {
      /* ignore */
    }
  }

  const t: TFunc = (key, vars) => {
    const val = DICTS[lang]?.[key] ?? DICTS.de[key] ?? key
    return interpolate(val, vars)
  }

  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>
}

export function useT(): I18nValue {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useT must be used within I18nProvider')
  return ctx
}
