import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { DialogsProvider } from './components/ui/dialogs'
import { I18nProvider } from './i18n'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      // v5-Default ist true → bei jedem Tab-Wechsel zurück zum Browser wurden
      // ALLE geladenen Galerie-Seiten neu geholt (bei 20 Seiten × 100 Fotos
      // = 10 MB nutzloser Traffic). Für eine Foto-Bibliothek unnötig aggressiv.
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <BrowserRouter>
          <DialogsProvider>
            <App />
          </DialogsProvider>
        </BrowserRouter>
      </I18nProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
