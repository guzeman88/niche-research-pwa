import { display } from '../lib/productValidation'

export default function ValidationImportPreview({rows}: {rows: Array<Record<string, unknown>>}) {
  if (!rows.length) return null
  const columns = ['order_id', 'transaction_id', 'listing_id', 'date', 'period_start', 'period_end', 'currency', 'visits', 'orders', 'revenue'].filter(key => key in rows[0])
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="pb-3 text-left text-surface-200">Preview of the first {Math.min(rows.length, 10)} rows. Confirm identities, dates, currency and totals before importing.</caption><thead><tr>{columns.map(key => <th key={key} className="px-3 py-2 font-medium">{key.replace(/_/g, ' ')}</th>)}</tr></thead><tbody>{rows.slice(0, 10).map((row, index) => <tr key={index}>{columns.map(key => <td key={key} className="whitespace-nowrap border-t border-surface-700 px-3 py-3">{row[key] == null ? 'Unknown' : typeof row[key] === 'number' ? display(row[key] as number) : String(row[key])}</td>)}</tr>)}</tbody></table></div>
}
