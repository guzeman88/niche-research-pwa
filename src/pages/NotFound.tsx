import { Link } from 'react-router-dom'
import Icon from '../components/Icon'

export default function NotFound() {
  return (
    <div className="p-6 flex items-center justify-center h-full">
      <div className="card text-center py-12 max-w-md">
        <div className="text-4xl mb-3"><Icon name="search" size={48} className="text-primary-200" /></div>
        <h2 className="text-lg font-bold text-white mb-2">Page Not Found</h2>
        <p className="text-sm text-surface-300 mb-4">
          This niche hasn't been researched yet.
        </p>
        <Link to="/" className="btn-primary">Back to Dashboard</Link>
      </div>
    </div>
  )
}
