import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSettings, updateSettings, getAdapterStatus, getExportCsvUrl, getExportJsonUrl } from '../lib/api'
import Icon from '../components/Icon'
import type { AdapterStatus } from '../types/api'

export default function Settings() {
  const queryClient = useQueryClient()

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const { data: adapters } = useQuery<AdapterStatus>({
    queryKey: ['adapter-status'],
    queryFn: getAdapterStatus,
    refetchInterval: 10_000,
  })

  const saveMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['settings'] }),
  })

  return (
    <div className="p-4 lg:p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-surface-50">Settings</h2>
        <p className="text-sm text-surface-300 mt-1">Configuration and adapter status</p>
      </div>

      {/* Adapter status */}
      <div className="card">
        <h3 className="text-sm font-semibold text-surface-100 mb-3">Adapter Status</h3>
        <div className="space-y-2">
          {adapters && Object.entries(adapters).map(([name, status]) => (
            <div key={name} className="flex items-center justify-between py-2 border-b border-surface-500 last:border-0">
              <span className="text-sm text-surface-200">{name}</span>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${status.healthy ? 'bg-emerald-400' : status.available ? 'bg-amber-400' : 'bg-red-400'}`} />
                <span className={`text-xs ${status.healthy ? 'text-accent-green' : status.available ? 'text-accent-amber' : 'text-accent-red'}`}>
                  {status.healthy ? 'Healthy' : status.available ? 'Not configured' : 'Unavailable'}
                </span>
              </div>
            </div>
          ))}
          {(!adapters || Object.keys(adapters).length === 0) && (
            <p className="text-sm text-surface-300">No adapter status available</p>
          )}
        </div>
      </div>

      {/* Scoring weights */}
      <div className="card">
        <h3 className="text-sm font-semibold text-surface-100 mb-3">Scoring Configuration</h3>
        {settings?.settings?.niche_scoring ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(settings.settings.niche_scoring as Record<string, number>).map(([key, value]) => (
              <div key={key} className="p-3 rounded-lg bg-surface-700/50">
                <div className="text-xs text-surface-300 mb-1">{key.replace(/_/g, ' ')}</div>
                <div className="text-lg font-bold text-surface-50">{value}</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-surface-300">Load settings.yaml to configure scoring weights</p>
        )}
      </div>

      {/* Export */}
      <div className="card">
        <h3 className="text-sm font-semibold text-surface-100 mb-3">Export Data</h3>
        <div className="flex flex-wrap gap-3">
          <a href={getExportCsvUrl()} className="btn-secondary" download><Icon name="download" size={16} /> Export CSV</a>
          <a href={getExportJsonUrl()} className="btn-secondary" download><Icon name="download" size={16} /> Export JSON</a>
          <a href={getExportJsonUrl(true)} className="btn-secondary" download><Icon name="download" size={16} /> Export JSON (with scans)</a>
        </div>
      </div>

      {/* Backend info */}
      <div className="card">
        <h3 className="text-sm font-semibold text-surface-100 mb-2">Backend</h3>
        <p className="text-xs text-surface-300">
          The API server must be running to use the research features.
          Start it with: <code className="text-primary-200 bg-surface-700 px-1.5 py-0.5 rounded">cd backend && uvicorn main:app --reload</code>
        </p>
      </div>
    </div>
  )
}
