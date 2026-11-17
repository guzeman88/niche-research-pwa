import {useEffect, useRef, useState} from 'react'

import type {ReactNode} from 'react'

import {DrawerContext} from './drawerContext'
import {useLocation} from 'react-router-dom'



const paths = {grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',file:'M14 2H5v20h14V7zM14 2v6h5M8 13h8M8 17h6',layers:'M12 2l10 5-10 5L2 7zM2 12l10 5 10-5M2 17l10 5 10-5',check:'M4 12l5 5L20 5',chart:'M4 3v17h17M8 15l4-5 4 2 5-7',account:'M20 21a8 8 0 0 0-16 0M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',next:'M10 6l6 6-6 6',close:'M6 6l12 12M18 6L6 18',lock:'M6 10h12v11H6zM8 10V6a4 4 0 0 1 8 0v4',box:'M3 7l9-5 9 5v10l-9 5-9-5zM3 7l9 5 9-5M12 12v10'}

export function PipelineIcon({name}:{name:keyof typeof paths}) {return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>}

export function Facts({rows}:{rows:Array<[string,ReactNode]>}){return <dl className="facts">{rows.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v??'Unknown'}</dd></div>)}</dl>}

export function Pill({children,warning=false}:{children:ReactNode;warning?:boolean}){return <span className={`pill${warning?' warning':''}`}>{children}</span>}

export function Table({heads,rows}:{heads:string[];rows:ReactNode[][]}){return <div className="table-scroll" role="region" tabIndex={0} aria-label={heads.filter(Boolean).join(', ')}><table><thead><tr>{heads.map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{rows.length?rows.map((row,i)=><tr key={i}>{row.map((c,j)=><td key={j}>{c}</td>)}</tr>):<tr><td colSpan={heads.length}><div className="empty"><h2>No matching records</h2></div></td></tr>}</tbody></table></div>}

export function Heading({title,actions}:{title:string;actions?:ReactNode}){return <header className="page-heading"><h1>{title}</h1><div className="heading-actions">{actions}</div></header>}

export function QueryState({pending,error,retry}:{pending:boolean;error:Error|null;retry:()=>unknown}){return pending?<div role="status" aria-busy="true">Loading records…</div>:error?<div role="alert" className="pipeline-error"><h2>Data unavailable</h2><div>{error.message}</div><button className="button" onClick={()=>void retry()}>Retry connection</button></div>:null}



type Drawer={title:string;body:ReactNode;origin:HTMLElement|null;routeKey:string}

export function PipelineProvider({children}:{children:ReactNode}){

 const location=useLocation()
 const [drawer,setDrawer]=useState<Drawer|null>(null)

 const panel=useRef<HTMLElement>(null)

 const close=()=>{const origin=drawer?.origin;setDrawer(null);requestAnimationFrame(()=>origin?.isConnected&&origin.focus())}

 useEffect(()=>{

  if(!drawer||drawer.routeKey!==location.key)return

  const el=panel.current!,shell=document.querySelector<HTMLElement>('.app-shell')!,media=matchMedia('(max-width:700px)')

  const sync=()=>{shell.inert=media.matches;if(media.matches){el.setAttribute('role','dialog');el.setAttribute('aria-modal','true')}else{el.removeAttribute('role');el.removeAttribute('aria-modal')}}

  sync();el.querySelector<HTMLButtonElement>('.close')?.focus();media.addEventListener('change',sync)

  const keys=(ev:KeyboardEvent)=>{if(ev.key==='Escape'){ev.preventDefault();const origin=drawer.origin;setDrawer(null);shell.inert=false;requestAnimationFrame(()=>origin?.isConnected&&origin.focus())}if(ev.key==='Tab'&&media.matches){const items=[...el.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]')].filter(x=>x.checkVisibility());const first=items[0],last=items[items.length-1];if(ev.shiftKey&&(document.activeElement===first||!el.contains(document.activeElement))){ev.preventDefault();last?.focus()}else if(!ev.shiftKey&&(document.activeElement===last||!el.contains(document.activeElement))){ev.preventDefault();first?.focus()}}}

  document.addEventListener('keydown',keys)

  return()=>{shell.inert=false;media.removeEventListener('change',sync);document.removeEventListener('keydown',keys)}

 },[drawer,location.key])

 return <DrawerContext.Provider value={(title,body)=>setDrawer(prior=>({title,body,origin:prior?.routeKey===location.key?prior.origin:document.activeElement as HTMLElement,routeKey:location.key}))}>{children}{drawer&&drawer.routeKey===location.key&&<aside ref={panel} className="detail-panel" aria-labelledby="pipeline-detail-title"><button className="close" onClick={close} aria-label="Close details"><PipelineIcon name="close"/></button><h2 id="pipeline-detail-title">{drawer.title}</h2><div className="pipeline-detail-body">{drawer.body}</div></aside>}</DrawerContext.Provider>

}
