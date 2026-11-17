import {createContext,useContext} from 'react'

import type {ReactNode} from 'react'

export const DrawerContext=createContext<(title:string,body:ReactNode)=>void>(()=>{})

export const usePipelineDrawer=()=>useContext(DrawerContext)
