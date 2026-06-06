/** Format a number with commas */
export function fmt(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '—';
  return n.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

/** Format a USD price */
export function fmtPrice(n: number | null | undefined): string {
  if (n == null || n === 0) return '—';
  return `$${n.toFixed(2)}`;
}

/** Get a Tailwind color class for an opportunity score (0-100) */
export function scoreColor(score: number): string {
  if (score >= 70) return 'text-emerald-400';
  if (score >= 50) return 'text-amber-400';
  return 'text-red-400';
}

/** Get a Tailwind bg color class for score badges */
export function scoreBg(score: number): string {
  if (score >= 70) return 'bg-emerald-500/20';
  if (score >= 50) return 'bg-amber-500/20';
  return 'bg-red-500/20';
}

/** Format a date string for display */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Format a date + time */
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Month number → name */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function monthName(n: number): string {
  return MONTHS[n - 1] || '?';
}

/** Truncate a string */
export function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n) + '…';
}
