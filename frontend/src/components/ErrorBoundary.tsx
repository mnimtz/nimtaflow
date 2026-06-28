import { Component, ReactNode } from 'react'

/** Catches render errors in a page so ONE broken page degrades to a message
 *  instead of white-screening the whole app (there was no boundary before, so a
 *  single throw — e.g. the Pipeline page's ws:// mixed-content error — blanked
 *  everything). Resets when the route changes via the `resetKey` prop. */
export default class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) { return { error } }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3 text-center px-6">
          <div className="text-lg font-semibold text-gray-700 dark:text-gray-200">
            Diese Seite konnte nicht geladen werden
          </div>
          <div className="text-sm text-gray-500 max-w-md break-words">
            {this.state.error.message}
          </div>
          <button onClick={() => location.reload()}
            className="mt-2 px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm hover:bg-indigo-500">
            Neu laden
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
