import {useEffect,useState} from 'react'
import {flushAccountWorkspace,subscribeWorkspace,workspaceStatus} from '../../lib/accountWorkspace'
import {downloadBackup} from '../../lib/workspaceBackup'
export default function WorkspaceSaveStatus(){
  const [state,setState]=useState(workspaceStatus)
  useEffect(()=>subscribeWorkspace(()=>setState(workspaceStatus())),[])
  if(!state.owner)return null
  return <div className="px-4 py-2 text-xs border-b border-surface-600 bg-surface-900" role={state.error?'alert':'status'}>
    {state.error?<div className="flex flex-wrap items-center gap-3"><span className="text-red-200">{state.error}</span><button className="btn-secondary" onClick={()=>downloadBackup()}>Download unsaved work</button><button className="btn-secondary" onClick={()=>void flushAccountWorkspace().catch(()=>{})}>Retry save</button></div>:<span className="text-surface-200">{state.saving?'Saving your workspace…':state.dirty?'Changes waiting to save…':'Workspace saved to your account'}</span>}
  </div>
}
