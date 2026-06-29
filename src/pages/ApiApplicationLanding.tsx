import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icon'

const WEBSITE_URL = 'https://etsy-niches.netlify.app/api-application'
const CALLBACK_URL = 'https://etsy-niches.netlify.app/auth/etsy'

const SCREENSHOTS = [
  {
    title: 'Research dashboard',
    text: 'Keyword coverage, opportunity distribution, gap signals, and active niche leads in one review surface.',
    src: '/screenshots/dashboard.png',
    alt: 'Etsy Pipeline dashboard showing keyword coverage and opportunity metrics',
  },
  {
    title: 'User scan import',
    text: 'Sellers can import their own eRank, Semrush, CSV, or manual keyword rows for private analysis.',
    src: '/screenshots/keyword-import.png',
    alt: 'User mode keyword importer for eRank, Semrush, CSV, and manual keyword scans',
  },
  {
    title: 'Store idea generator',
    text: 'Store concepts are generated from keyword clusters and can be saved into product and listing workflows.',
    src: '/screenshots/store-generator.png',
    alt: 'Store idea generator showing keyword-backed store concepts',
  },
]

const FEATURES = [
  { icon: 'search' as const, title: 'Keyword research', text: 'Import and compare keyword evidence from seller-approved research sources.' },
  { icon: 'layers' as const, title: 'Niche clustering', text: 'Group related searches into focused store concepts and product directions.' },
  { icon: 'package' as const, title: 'Product planning', text: 'Turn selected keywords into product ideas, design prompts, and listing drafts.' },
  { icon: 'file-text' as const, title: 'Listing workflow', text: 'Organize titles, tags, descriptions, and validation notes before publishing.' },
]

const API_USES = [
  'Connect an Etsy shop through OAuth so the seller controls authorization.',
  'Read the connected shop data needed to plan products, listings, traffic review, and listing management workflows.',
  'Keep imported keyword research and generated planning work scoped to the user workspace.',
  'Support future listing draft and shop-management actions only for the authenticated seller account.',
]

export default function ApiApplicationLanding() {
  useEffect(() => {
    document.title = 'Etsy Pipeline - API Application'
  }, [])

  return (
    <main className="min-h-screen bg-surface-950 text-surface-50">
      <section className="relative min-h-[88vh] overflow-hidden">
        <img
          src="/screenshots/dashboard.png"
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-cover opacity-[0.34]"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(20,25,33,0.96),rgba(20,25,33,0.76)_48%,rgba(20,25,33,0.52)),linear-gradient(180deg,rgba(20,25,33,0.36),#202631)]" />

        <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary-300/30 bg-primary-400/12 text-primary-100">
              <Icon name="search" size={17} />
            </span>
            <span className="text-[14px] font-extrabold tracking-tight text-surface-50">Etsy Pipeline</span>
          </div>
          <Link className="btn-secondary min-h-10 px-3 py-2 text-[12px]" to="/">
            Open App
          </Link>
        </header>

        <div className="relative z-10 mx-auto flex min-h-[calc(88vh-5rem)] w-full max-w-6xl items-center px-5 pb-14 pt-6 sm:px-6 lg:px-8">
          <div className="max-w-3xl">
            <p className="mb-4 inline-flex rounded-md border border-primary-300/25 bg-primary-400/10 px-3 py-1 text-[11px] font-extrabold uppercase tracking-wider text-primary-100">
              Etsy seller research and listing planning
            </p>
            <h1 className="max-w-3xl text-4xl font-extrabold leading-[1.04] tracking-tight text-surface-50 sm:text-5xl lg:text-6xl">
              Etsy Pipeline
            </h1>
            <p className="mt-5 max-w-2xl text-[16px] leading-7 text-surface-200 sm:text-[18px]">
              A private workspace for Etsy shop owners to import keyword research, find niche opportunities, generate store and product ideas, and prepare listing drafts before publishing.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <a className="btn-primary min-h-11 px-4 py-2.5 text-[13px]" href="#api-use">
                <Icon name="key" size={15} />
                API Use
              </a>
              <a className="btn-secondary min-h-11 px-4 py-2.5 text-[13px]" href="#screenshots">
                <Icon name="grid" size={15} />
                Screenshots
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-surface-600/55 bg-surface-900/45 px-5 py-5 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-6xl gap-3 md:grid-cols-3">
          <InfoTile label="Website URL" value={WEBSITE_URL} />
          <InfoTile label="OAuth Callback" value={CALLBACK_URL} />
          <InfoTile label="Access Model" value="OAuth, seller-authorized" />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-5 py-14 sm:px-6 lg:px-8" id="screenshots">
        <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="section-label">Product Screenshots</p>
            <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-surface-50">What sellers use</h2>
          </div>
          <p className="max-w-xl text-[13px] leading-6 text-surface-300">
            The app separates developer research from user-scoped keyword imports, then uses keyword evidence to guide store and product planning.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {SCREENSHOTS.map((shot) => (
            <article key={shot.title} className="overflow-hidden rounded-lg border border-surface-600/65 bg-surface-800/80 shadow-[0_14px_34px_rgba(7,10,14,0.2)]">
              <img src={shot.src} alt={shot.alt} className="aspect-[16/10] w-full object-cover object-left-top" loading="lazy" />
              <div className="p-4">
                <h3 className="text-[14px] font-extrabold text-surface-50">{shot.title}</h3>
                <p className="mt-2 text-[12px] leading-5 text-surface-300">{shot.text}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="bg-surface-900/35 px-5 py-14 sm:px-6 lg:px-8">
        <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="rounded-lg border border-surface-600/55 bg-surface-800/70 p-4">
              <Icon name={feature.icon} size={18} className="text-primary-100" />
              <h3 className="mt-3 text-[14px] font-extrabold text-surface-50">{feature.title}</h3>
              <p className="mt-2 text-[12px] leading-5 text-surface-300">{feature.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-8 px-5 py-14 sm:px-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:px-8" id="api-use">
        <div>
          <p className="section-label">Etsy API Application</p>
          <h2 className="mt-2 text-2xl font-extrabold tracking-tight text-surface-50">How the API is used</h2>
          <p className="mt-4 text-[14px] leading-6 text-surface-300">
            Etsy Pipeline uses Etsy OAuth so each seller explicitly authorizes access to their own shop data. The app is designed for seller research, listing planning, and shop-management workflows controlled by the connected account.
          </p>
        </div>
        <div className="rounded-lg border border-surface-600/65 bg-surface-800/85 p-4">
          <div className="space-y-3">
            {API_USES.map((item) => (
              <div key={item} className="flex gap-3 rounded-md border border-surface-600/40 bg-surface-950/20 p-3">
                <Icon name="check-circle" size={15} className="mt-0.5 flex-shrink-0 text-accent-green" />
                <p className="text-[12px] leading-5 text-surface-200">{item}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-surface-600/55 px-5 py-8 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-lg border border-surface-600/65 bg-surface-900/60 p-4">
            <h2 className="text-[13px] font-extrabold text-surface-100">Disclaimer</h2>
            <p className="mt-2 text-[12px] leading-5 text-surface-300">
              The term "Etsy" is a trademark of Etsy, Inc. This application uses the Etsy API but is not endorsed or certified by Etsy, Inc.
            </p>
          </div>
          <footer className="flex flex-col gap-3 py-6 text-[12px] text-surface-400 sm:flex-row sm:items-center sm:justify-between">
            <span>Etsy Pipeline - private seller workflow software</span>
            <Link className="font-bold text-primary-100 hover:text-primary-200" to="/auth/etsy">OAuth callback page</Link>
          </footer>
        </div>
      </section>
    </main>
  )
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-surface-600/55 bg-surface-800/70 p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-surface-400">{label}</div>
      <div className="mt-1 break-all text-[12px] font-extrabold text-surface-100">{value}</div>
    </div>
  )
}
