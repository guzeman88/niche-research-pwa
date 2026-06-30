interface BrandMarkProps {
  className?: string
  title?: string
}

interface BrandLogoProps {
  className?: string
  markClassName?: string
  wordmarkClassName?: string
  subtitle?: string
}

export function BrandMark({ className = 'h-8 w-8', title }: BrandMarkProps) {
  const titleId = title ? 'etgen-mark-title' : undefined

  return (
    <svg
      className={className}
      viewBox="0 0 96 96"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-labelledby={titleId}
      focusable="false"
    >
      {title && <title id={titleId}>{title}</title>}
      <rect x="16" y="16" width="64" height="64" rx="16" fill="rgba(111,150,200,.12)" stroke="rgba(190,210,234,.55)" strokeWidth="2" />
      <circle cx="42" cy="44" r="15" fill="none" stroke="#bed2ea" strokeWidth="5" />
      <path d="m53 55 13 13" stroke="#9fb9dc" strokeWidth="5" strokeLinecap="round" />
      <path d="M32 50 41 39l7 7 14-16" fill="none" stroke="#a9c88f" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function BrandLogo({
  className = '',
  markClassName = 'h-8 w-8',
  wordmarkClassName = 'text-[15px] font-extrabold leading-none tracking-tight',
  subtitle,
}: BrandLogoProps) {
  return (
    <div className={`flex min-w-0 items-center gap-2.5 ${className}`} aria-label="EtGen">
      <span className="flex flex-shrink-0 items-center justify-center rounded-lg border border-primary-400/30 bg-primary-400/10">
        <BrandMark className={markClassName} />
      </span>
      <span className="min-w-0">
        <span className={`block truncate ${wordmarkClassName}`}>
          <span className="text-surface-50">Et</span><span className="text-primary-300">Gen</span>
        </span>
        {subtitle && <span className="mt-1 block truncate text-[11px] font-medium text-surface-300">{subtitle}</span>}
      </span>
    </div>
  )
}
