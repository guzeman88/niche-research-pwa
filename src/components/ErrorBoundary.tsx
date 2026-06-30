import { Component, type ReactNode } from 'react'
import Icon from './Icon'
import { isChunkLoadError, refreshForCurrentAssets } from '../chunkRecovery'
import BrandLogo from './BrandLogo'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error) {
    refreshForCurrentAssets(error)
  }

  render() {
    if (this.state.hasError) {
      const isAssetError = isChunkLoadError(this.state.error)

      return (
        <div className="min-h-screen flex items-center justify-center bg-surface-800 p-6">
          <div className="card max-w-md text-center space-y-4">
            <div className="flex justify-center">
              <BrandLogo className="justify-center" markClassName="h-9 w-9" wordmarkClassName="text-lg font-extrabold leading-none tracking-tight" />
            </div>
            <div className="flex justify-center text-primary-200"><Icon name="alert-triangle" size={34} /></div>
            <h2 className="text-lg font-bold text-surface-50">
              {isAssetError ? 'Refreshing app' : 'Something went wrong'}
            </h2>
            <p className="text-sm text-surface-200">
              {isAssetError ? 'The app updated while this window was open.' : (this.state.error?.message || 'An unexpected error occurred')}
            </p>
            {!isAssetError && (
              <p className="text-xs text-surface-400">
                Reload the app. Static keyword data will still work if the backend is unavailable.
              </p>
            )}
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null })
                window.location.replace(`/?v=17&manual_refresh=${Date.now()}`)
              }}
              className="btn-primary"
            >
              Reload EtGen
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
