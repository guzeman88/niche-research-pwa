import ProductionQueue from '../components/ProductionQueue'
import ProductionSellerConnection from '../components/ProductionSellerConnection'
export default function Production(){return <div className="page"><h1 className="text-2xl font-semibold">Production</h1><p className="mt-3 max-w-2xl text-base leading-relaxed text-surface-200">Turn a reviewed product brief into customer files, inspect the result and approve the exact revision before export.</p><ProductionSellerConnection/><ProductionQueue/></div>}
