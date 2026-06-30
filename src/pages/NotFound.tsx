import { Link } from 'react-router-dom'
import { BrandMark } from '../components/BrandLogo'

export default function NotFound() {
  return (
    <div className="p-6 flex items-center justify-center h-full">
      <div className="card text-center py-12 max-w-md">
        <div className="mb-3 flex justify-center"><BrandMark className="h-12 w-12" /></div>
        <h2 className="text-lg font-bold text-white mb-2">Page Not Found</h2>
        <p className="text-sm text-surface-300 mb-4">
          This niche hasn't been researched yet.
        </p>
        <Link to="/" className="btn-primary">Back to Dashboard</Link>
      </div>
    </div>
  )
}
