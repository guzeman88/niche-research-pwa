import {useMutation,useQuery} from '@tanstack/react-query'
import {accountRequest} from '../lib/accountApi'
import {productionRequest} from '../lib/production'

interface ConnectionStatus {configured:boolean;connected:boolean;expected_shop?:string;shop_name?:string;reason?:string;status?:string;draft_upload_verified?:boolean}
interface OwnOrders {status:string;receipts:number|null;paid_receipts:number|null;gross_paid_units:number|null;support_minutes_per_order:number|null;checked_at:number|null;sample_orders:Array<{order_key:string;support_minutes:number|null}>}
export default function ProductionSellerConnection(){
  const status=useQuery({queryKey:['production-seller'],queryFn:()=>productionRequest<ConnectionStatus>('/etsy/status'),retry:false,refetchInterval:30000})
  const orders=useQuery({queryKey:['production-own-orders'],queryFn:()=>productionRequest<OwnOrders>('/etsy/orders'),enabled:status.data?.connected===true,retry:false,refetchInterval:60000})
  const connect=useMutation({mutationFn:()=>accountRequest<{authorize_url:string}>('/etsy/start',{}),onSuccess:data=>{window.location.assign(data.authorize_url)}})
  const sync=useMutation({mutationFn:()=>productionRequest('/etsy/orders/sync',{}),onSuccess:()=>{void orders.refetch()}})
  const support=useMutation({mutationFn:(body:unknown)=>productionRequest('/etsy/orders/support',body),onSuccess:()=>{void orders.refetch()}})
  const callback=new URLSearchParams(location.search).get('etsy_connection')
  return <section aria-labelledby="seller-connection-heading" className="mt-8 space-y-4 border-y border-surface-600 py-6">
    <h2 id="seller-connection-heading" className="text-xl font-semibold">Etsy connection</h2>
    {status.isPending&&<p role="status" className="text-sm text-surface-200">Checking the private seller connection…</p>}
    {status.data&&<><p className="max-w-prose text-sm">{status.data.connected?`Connected to ${status.data.shop_name}. Own-order reading is verified. Draft upload still follows exact-product approval.`:status.data.configured?`Connect the seller who owns ${status.data.expected_shop}. Etsy will show the requested permissions.`:'Seller connection needs operator setup. Your saved products remain available.'}</p>
      {!status.data.connected&&<button className="btn-secondary" disabled={!status.data.configured||connect.isPending} onClick={()=>connect.mutate()}>{connect.isPending?'Opening Etsy…':'Connect Etsy seller'}</button>}
      <p className="max-w-prose text-sm text-surface-200">This connection can read your shop orders and create approved listing drafts. Automatic publication, advertising purchases and fulfillment orders remain disabled.</p>
      {!status.data.configured&&status.data.reason&&<p className="text-sm text-surface-200">{status.data.reason}</p>}
    </>}
    {callback&&callback!=='connected'&&!status.data?.connected&&<p role="alert" className="text-sm">The Etsy connection was {callback==='cancelled'?'cancelled':'not completed'}. Check the seller account and retry.</p>}
    {status.data?.connected&&<details><summary className="cursor-pointer text-sm font-semibold">Own orders and cost measurements</summary><div className="mt-4 space-y-4">
      <p className="max-w-prose text-sm text-surface-200">Orders refresh through the backend’s collection schedule. Buyer names, emails, addresses and messages are not retained. Missing measurements remain unknown.</p>
      {orders.data&&<dl className="grid gap-4 sm:grid-cols-3"><div><dt className="text-sm text-surface-200">Captured receipts</dt><dd className="mt-1 font-semibold tabular-nums">{orders.data.receipts??'Unknown'}</dd></div><div><dt className="text-sm text-surface-200">Gross paid units</dt><dd className="mt-1 font-semibold tabular-nums">{orders.data.gross_paid_units??'Unknown'}</dd></div><div><dt className="text-sm text-surface-200">Support minutes per paid order</dt><dd className="mt-1 font-semibold tabular-nums">{orders.data.support_minutes_per_order?.toFixed(1)??'Not measured'}</dd></div></dl>}
      <button className="btn-secondary" disabled={sync.isPending} onClick={()=>sync.mutate()}>{sync.isPending?'Refreshing…':'Refresh own orders'}</button>
      {orders.data?.sample_orders.length? <form className="max-w-xl space-y-3" onSubmit={event=>{event.preventDefault();const data=new FormData(event.currentTarget);support.mutate({order_key:data.get('order_key'),minutes:Number(data.get('minutes'))})}}>
        <label className="block text-sm">Captured order<select className="input mt-2 w-full" name="order_key">{orders.data.sample_orders.map(order=><option key={order.order_key} value={order.order_key}>{order.order_key.slice(0,12)} · {order.support_minutes===null?'time unknown':order.support_minutes+' minutes'}</option>)}</select></label>
        <label className="block text-sm">Observed support minutes<input className="input mt-2 w-full" type="number" name="minutes" min="0" max="1440" step="any" required/></label>
        <p className="text-xs text-surface-200">Enter zero only when you know no support was needed. Include every paid order when measuring average support cost.</p><button className="btn-secondary" disabled={support.isPending}>Save observed support time</button>
      </form>:<p className="text-sm text-surface-200">No captured paid orders are available for support logging.</p>}
      <p className="max-w-prose text-sm text-surface-200">Receipt capture does not establish actual profit, net units after refunds, or sales-estimator accuracy. Payment charges still need reconciliation.</p>
    </div></details>}
    {[status.error,connect.error,orders.error,sync.error,support.error].filter(Boolean).map((error,index)=><p role="alert" className="text-sm" key={index}>{error?.message}</p>)}
  </section>
}
