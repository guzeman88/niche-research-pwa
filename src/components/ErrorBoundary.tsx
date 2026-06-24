import { Component, type ReactNode } from 'react'
import Icon from './Icon'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-surface-800 p-6">
          <div className="card max-w-md text-center space-y-4">
            <div className="text-4xl"><Icon name="alert-triangle" size={48} /></div>
            <h2 className="text-lg font-bold text-surface-50">Something went wrong</h2>
            <p className="text-sm text-surface-200">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
            <p className="text-xs text-surface-400">
              Make sure the backend is running at the configured API URL.
            </p>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload() }}
              className="btn-primary"
            >
              Reload App
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
