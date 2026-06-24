/** Premium shimmer skeleton components for loading states */

// ── Base shimmer ────────────────────────────────────────────────────────

function Shimmer({ className = '', ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`relative overflow-hidden bg-surface-800/70 rounded-lg ${className}`}
      {...props}
    >
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.5s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-white/[0.04] to-transparent" />
    </div>
  )
}

// ── Dashboard skeletons ─────────────────────────────────────────────────

export function DashboardSkeleton() {
  return (
    <div className="p-4 lg:p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Shimmer className="w-24 h-4" />
          <Shimmer className="w-40 h-6" />
        </div>
        <Shimmer className="w-28 h-9 rounded-lg" />
      </div>

      {/* Chip stats row */}
      <div className="flex gap-2.5 overflow-x-auto pb-1">
        {[120, 100, 110, 90].map((w, i) => (
          <Shimmer key={i} className="h-[68px] rounded-lg flex-shrink-0" style={{ width: w }} />
        ))}
      </div>

      {/* Big metric cards */}
      <div className="grid grid-cols-2 gap-2.5">
        {[1,2,3,4].map(i => (
          <Shimmer key={i} className="h-[100px] rounded-lg" />
        ))}
      </div>

      {/* Chart + Gap cards */}
      <div className="grid lg:grid-cols-2 gap-5">
        <Shimmer className="h-[200px] rounded-lg" />
        <Shimmer className="h-[200px] rounded-lg" />
      </div>

      {/* Section header + ranked list */}
      <Shimmer className="w-32 h-4 mt-2" />
      <div className="space-y-2">
        {[1,2,3,4,5,6].map(i => (
          <div key={i} className="flex items-center gap-3">
            <Shimmer className="w-6 h-6 rounded-lg flex-shrink-0" />
            <Shimmer className="h-5 flex-1 rounded-lg" style={{ maxWidth: `${90 - i * 8}%` }} />
            <Shimmer className="w-12 h-5 rounded-lg flex-shrink-0" />
            <Shimmer className="w-12 h-4 rounded-lg flex-shrink-0 hidden sm:block" />
          </div>
        ))}
      </div>

      {/* Domain + Breakout section */}
      <div className="grid lg:grid-cols-2 gap-5">
        <Shimmer className="h-[180px] rounded-lg" />
        <Shimmer className="h-[180px] rounded-lg" />
      </div>
    </div>
  )
}

// ── Keywords skeleton ───────────────────────────────────────────────────

export function KeywordsSkeleton() {
  return (
    <div className="p-4 lg:p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Shimmer className="w-24 h-6" />
          <Shimmer className="w-32 h-4" />
        </div>
        <Shimmer className="w-28 h-9 rounded-lg" />
      </div>

      {/* Search + filter */}
      <div className="flex gap-2">
        <Shimmer className="h-10 flex-1 rounded-lg" />
        <Shimmer className="h-10 w-36 rounded-lg" />
      </div>

      {/* Table */}
      <div className="panel overflow-hidden">
        {/* Table header */}
        <div className="flex gap-4 px-4 py-3 border-b border-surface-600 bg-surface-900/55">
          {['Keyword','Domain','Status','Opp','Gap','Trend'].map((h, i) => (
            <div key={h} className="flex-1" style={{ maxWidth: i === 0 ? 200 : i === 1 ? 100 : 80 }}>
              <Shimmer className="h-3 w-full" style={{ maxWidth: i === 0 ? 60 : i === 1 ? 50 : 40 }} />
            </div>
          ))}
        </div>
        {/* Table rows */}
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="flex gap-4 px-4 py-3 border-b border-surface-600/30">
            <Shimmer className="h-4 flex-1 rounded" style={{ maxWidth: 160 - i * 3 }} />
            <Shimmer className="h-5 w-20 rounded-lg flex-shrink-0" />
            <Shimmer className="h-4 w-16 rounded flex-shrink-0" />
            <Shimmer className="h-4 w-10 rounded flex-shrink-0" />
            <Shimmer className="h-4 w-10 rounded flex-shrink-0" />
            <Shimmer className="h-4 w-12 rounded flex-shrink-0" />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Stores skeleton ─────────────────────────────────────────────────────

export function StoresSkeleton() {
  return (
    <div className="flex h-full">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex flex-col w-80 flex-shrink-0 border-r border-surface-600/60 bg-surface-900/45 p-4">
        <div className="mb-4">
          <Shimmer className="w-20 h-6 mb-1" />
          <Shimmer className="w-24 h-3" />
        </div>
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex items-center gap-3 p-3 mb-1">
            <Shimmer className="w-10 h-10 rounded-lg flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Shimmer className="h-4 rounded" style={{ width: `${80 - i * 5}%` }} />
              <Shimmer className="h-3 rounded" style={{ width: `${60 - i * 3}%` }} />
            </div>
          </div>
        ))}
      </div>

      {/* Mobile list */}
      <div className="lg:hidden p-4 w-full">
        <div className="mb-4">
          <Shimmer className="w-20 h-6 mb-1" />
          <Shimmer className="w-32 h-3" />
        </div>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="flex items-center gap-3.5 p-3.5 rounded-lg mb-1.5 border border-surface-600/60 bg-surface-800/55">
            <Shimmer className="w-10 h-10 rounded-lg flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Shimmer className="h-4 rounded w-44" />
              <Shimmer className="h-3 rounded w-56" />
            </div>
            <Shimmer className="w-5 h-5 rounded flex-shrink-0" />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Small inline skeletons ──────────────────────────────────────────────

export function ChartSkeleton({ height = 180 }: { height?: number }) {
  return <Shimmer className="rounded-lg" style={{ height }} />
}

export function CardSkeleton() {
  return <Shimmer className="h-24 rounded-lg" />
}

export function RowSkeleton({ width = '100%' }: { width?: string }) {
  return <Shimmer className="h-4 rounded" style={{ width }} />
}
