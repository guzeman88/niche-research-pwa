import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import BrandLogo from './BrandLogo'

interface LegalSection {
  title: string
  body: ReactNode
}

interface LegalDocumentProps {
  title: string
  summary: string
  updated: string
  sections: LegalSection[]
}

export default function LegalDocument({ title, summary, updated, sections }: LegalDocumentProps) {
  return (
    <main className="min-h-screen bg-surface-950 text-surface-50">
      <header className="border-b border-surface-600/60 bg-surface-900/75">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-5 py-5 sm:px-6 lg:px-8">
          <Link to="/api-application" aria-label="EtGen home">
            <BrandLogo markClassName="h-9 w-9" wordmarkClassName="text-[14px] font-extrabold leading-none tracking-tight" />
          </Link>
          <Link className="btn-secondary min-h-10 px-3 py-2 text-[12px]" to="/api-application">
            About EtGen
          </Link>
        </div>
      </header>

      <article className="mx-auto w-full max-w-3xl px-5 py-12 sm:px-6 sm:py-16 lg:px-8">
        <header className="border-b border-surface-600/60 pb-8">
          <h1 className="text-3xl font-extrabold tracking-tight text-surface-50 sm:text-4xl">{title}</h1>
          <p className="mt-4 max-w-[68ch] text-[15px] leading-7 text-surface-200">{summary}</p>
          <p className="mt-4 text-[12px] font-semibold text-surface-400">Last updated {updated}</p>
        </header>

        <div className="space-y-9 py-9">
          {sections.map((section) => (
            <section key={section.title} aria-labelledby={section.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}>
              <h2
                id={section.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}
                className="text-[17px] font-extrabold text-surface-50"
              >
                {section.title}
              </h2>
              <div className="mt-3 max-w-[72ch] space-y-3 text-[14px] leading-7 text-surface-200">
                {section.body}
              </div>
            </section>
          ))}
        </div>
      </article>

      <footer className="border-t border-surface-600/60 px-5 py-7 sm:px-6 lg:px-8">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 text-[12px] text-surface-300 sm:flex-row sm:items-center sm:justify-between">
          <span>EtGen · Private seller research and planning software</span>
          <nav className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Legal links">
            <Link className="font-bold text-primary-100 hover:text-primary-200" to="/privacy">Privacy</Link>
            <Link className="font-bold text-primary-100 hover:text-primary-200" to="/terms">Terms</Link>
          </nav>
        </div>
      </footer>
    </main>
  )
}
