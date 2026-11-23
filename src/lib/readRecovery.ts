import type {QueryClient} from '@tanstack/react-query'

export const recoveryInterval=(normal:number)=>(query:{state:{error:Error|null}})=>query.state.error?15000:normal
export function installReadRecovery(client:QueryClient){
 client.setQueryDefaults(['pipeline-artifact'],{refetchInterval:query=>query.state.error?15000:false,refetchOnWindowFocus:query=>Boolean(query.state.error),refetchOnReconnect:query=>Boolean(query.state.error)})
 for(const key of ['dashboard-summary','product-validation','production','pipeline-keywords','selling-discovery','selling-products','automatic-sales-estimates','pipeline-health','pipeline-reference-coverage','supported-keyword-goal','production-launch-recipes','test-candidate-portfolio','profitable-store-ideas','stores']){
  client.setQueryDefaults([key],{refetchOnWindowFocus:'always',refetchOnReconnect:'always',refetchInterval:recoveryInterval(60000)})
 }
}
