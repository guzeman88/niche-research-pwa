import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Explore from './pages/Explore'
import ReportDetail from './pages/ReportDetail'
import Keywords from './pages/Keywords'
import Scheduler from './pages/Scheduler'
import Settings from './pages/Settings'
import Stores from './pages/Stores'
import StoreGenerator from './pages/StoreGenerator'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/reports/:reportId" element={<ReportDetail />} />
        <Route path="/keywords" element={<Keywords />} />
        <Route path="/scheduler" element={<Scheduler />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/store-generator" element={<StoreGenerator />} />
        <Route path="/stores" element={<Stores />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
