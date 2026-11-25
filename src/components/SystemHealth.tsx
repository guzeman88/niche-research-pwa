import {useQuery} from '@tanstack/react-query'
import {accountRequest} from '../lib/accountApi'
import {Facts,QueryState} from '../pipeline/PipelineUI'
import {date,number,text} from '../pipeline/format'

interface Check {id:string;status:string;checked_at:string|null;stale:boolean;details:{database_bytes?:number;warning_bytes?:number;source_data_as_of?:string;keyword_count?:number}}
const labels:Record<string,string>={account_storage:'Account storage',private_backend:'Private backend',public_research:'Published research'}
export default function SystemHealth(){
 const local=['localhost','127.0.0.1','[::1]'].includes(location.hostname)
 const query=useQuery({queryKey:['system-health'],queryFn:()=>accountRequest<{checks:Check[]}>('/health'),enabled:!local,retry:false,refetchInterval:60000})
 if(local)return <a className="button" href="https://etgen.xyz/evidence">Open hosted system health</a>
 return <><QueryState pending={query.isPending} error={query.error} retry={query.refetch} retained={query.data!==undefined} lastUpdated={query.dataUpdatedAt}/>{query.data?.checks.map(check=><section className="drawer-section" key={check.id}><h3>{labels[check.id]||check.id}</h3><Facts rows={[["Status",text(check.status)],["Checked",date(check.checked_at)],...(check.id==='account_storage'?[["Database",check.details.database_bytes==null?'Unknown':number(Math.round(check.details.database_bytes/1000000))+' MB'],["Warning at",check.details.warning_bytes==null?'Unknown':number(check.details.warning_bytes/1000000)+' MB']]:check.id==='public_research'?[["Source observed",date(check.details.source_data_as_of)],["Keywords",number(check.details.keyword_count)]]:[]) as Array<[string,string]>]}/></section>)}</>
}
