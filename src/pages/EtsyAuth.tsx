import { useMemo, useState } from 'react'
import Icon from '../components/Icon'

type CopyState = 'idle' | 'copied' | 'failed'

function callbackUrl() {
  if (typeof window === 'undefined') return '/auth/etsy'
  return `${window.location.origin}/auth/etsy`
}

function queryValue(name: string) {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get(name) || ''
}

export default function EtsyAuth() {
  const [copyState, setCopyState] = useState<CopyState>('idle')
  const redirectUrl = useMemo(callbackUrl, [])
  const code = queryValue('code')
  const state = queryValue('state')
  const error = queryValue('error')
  const errorDescription = queryValue('error_description')
  const hasResponse = Boolean(code || error)

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopyState('copied')
      window.setTimeout(() => setCopyState('idle'), 1800)
    } catch {
      setCopyState('failed')
    }
  }

  return (
    <main className="min-h-screen bg-surface-950 px-4 py-6 text-surface-50 sm:px-6 lg:px-10">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] w-full max-w-3xl flex-col justify-center">
        <div className="mb-4 flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary-300/25 bg-primary-400/12 text-primary-100">
            <Icon name="key" size={18} />
          </span>
          <div>
            <h1 className="text-[18px] font-extrabold text-surface-50">Etsy Auth</h1>
            <p className="mt-0.5 text-[12px] font-medium text-surface-300">Redirect endpoint</p>
          </div>
        </div>

        <section className="panel overflow-hidden">
          <div className="border-b border-surface-600/60 px-4 py-3 sm:px-5">
            <div className="section-label">Callback URL</div>
          </div>

          <div className="space-y-4 p-4 sm:p-5">
            <div className="rounded-lg border border-surface-600/60 bg-surface-900/80 p-3">
              <p className="break-all font-mono text-[13px] leading-6 text-surface-100">{redirectUrl}</p>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <button className="btn-primary min-h-11" type="button" onClick={() => copy(redirectUrl)}>
                <Icon name="download" size={16} />
                {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy URL'}
              </button>
              <a
                className="btn-secondary min-h-11"
                href="https://www.etsy.com/developers/your-apps"
                rel="noreferrer"
                target="_blank"
              >
                <Icon name="external-link" size={16} />
                Etsy Apps
              </a>
            </div>
          </div>
        </section>

        <section className="panel mt-4 overflow-hidden">
          <div className="border-b border-surface-600/60 px-4 py-3 sm:px-5">
            <div className="section-label">Status</div>
          </div>

          <div className="space-y-3 p-4 sm:p-5">
            {!hasResponse && (
              <div className="flex items-start gap-3 rounded-lg border border-amber-400/20 bg-amber-400/10 p-3">
                <Icon name="clock" size={18} className="mt-0.5 text-amber-400" />
                <div>
                  <p className="text-[13px] font-bold text-surface-100">Ready</p>
                  <p className="mt-1 text-[12px] leading-5 text-surface-300">Use the URL above in Etsy.</p>
                </div>
              </div>
            )}

            {code && (
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/10 p-3">
                <div className="mb-2 flex items-center gap-2 text-[13px] font-bold text-surface-100">
                  <Icon name="check-circle" size={17} className="text-emerald-400" />
                  Code received
                </div>
                <button
                  className="w-full break-all rounded-lg border border-surface-600/60 bg-surface-900/80 p-3 text-left font-mono text-[12px] leading-5 text-surface-100"
                  type="button"
                  onClick={() => copy(code)}
                >
                  {code}
                </button>
              </div>
            )}

            {state && (
              <div className="rounded-lg border border-surface-600/55 bg-surface-900/70 p-3">
                <p className="text-[12px] font-bold text-surface-200">State</p>
                <p className="mt-1 break-all font-mono text-[12px] leading-5 text-surface-300">{state}</p>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-3 rounded-lg border border-red-400/25 bg-red-400/10 p-3">
                <Icon name="x-circle" size={18} className="mt-0.5 text-red-400" />
                <div>
                  <p className="text-[13px] font-bold text-surface-100">{error}</p>
                  {errorDescription && <p className="mt-1 text-[12px] leading-5 text-surface-300">{errorDescription}</p>}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}
