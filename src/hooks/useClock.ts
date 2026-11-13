import {useEffect,useState} from 'react'
export default function useClock(){
  const [time,setTime]=useState(()=>Date.now())
  useEffect(()=>{const timer=setInterval(()=>setTime(Date.now()),15000);return()=>clearInterval(timer)},[])
  return time
}
