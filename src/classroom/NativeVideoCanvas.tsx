import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { NativeVideoBus, NativeVideoDecoder, type NativeRenderedFrame } from './nativeVideo'
export function NativeVideo({bus,cameraId,generation,onPlaying,onFrame,overlayMatches,children}:{bus:NativeVideoBus;cameraId:string;generation:string;onPlaying:(playing:boolean)=>void;onFrame?:(frame:NativeRenderedFrame|null)=>void;overlayMatches?:(frame:NativeRenderedFrame)=>boolean;children?:ReactNode}) {
  const canvas=useRef<HTMLCanvasElement>(null)
  const overlay=useRef<HTMLDivElement>(null)
  const lastFrame=useRef<NativeRenderedFrame|null>(null)
  const callbacks=useRef({onPlaying,onFrame,overlayMatches})
  const gateOverlay=()=>{
    if(overlay.current){const visibility=lastFrame.current && callbacks.current.overlayMatches?.(lastFrame.current) ? 'visible':'hidden';if(overlay.current.style.visibility!==visibility)overlay.current.style.visibility=visibility}
  }
  useLayoutEffect(()=>{callbacks.current={onPlaying,onFrame,overlayMatches};gateOverlay()})
  useEffect(()=>{
    const canvasNode=canvas.current
    if(!canvasNode || typeof VideoDecoder==='undefined') return
    let last=-Infinity,playing=false,sampled=-Infinity
    let format:{width:number;height:number;videoGeneration:string;firstSourceMs:number}|null=null
    const show=(value:boolean)=>{if(value!==playing){playing=value;canvasNode.style.opacity=value?'1':'0';callbacks.current.onPlaying(value)}}
    let timer:ReturnType<typeof setTimeout>|undefined
    const clearFrame=()=>{if(lastFrame.current){lastFrame.current=null;callbacks.current.onFrame?.(null)}gateOverlay()}
    const expire=()=>{timer=undefined;gateOverlay();if(performance.now()-last>800){show(false);clearFrame()}else timer=setTimeout(expire,100)}
    const decoder=new NativeVideoDecoder(canvasNode,timestampMs=>{
      last=performance.now();show(true)
      if(format && canvasNode.width===format.width && canvasNode.height===format.height) {
        const frame={timestampMs,width:format.width,height:format.height,renderedAt:Date.now(),firstSourceMs:format.firstSourceMs,generation,videoGeneration:format.videoGeneration}
        lastFrame.current=frame
        // React receives at most10 source updates/sec. Visibility is checked on
        // every actual draw so a skeleton never outlives the180ms source match.
        if(last-sampled>=100){sampled=last;callbacks.current.onFrame?.(frame)}
      } else clearFrame()
      gateOverlay()
      if(timer===undefined)timer=setTimeout(expire,100)
    })
    const unsubscribe=bus.subscribe(cameraId,generation,packet=>{
      if(packet){format={width:packet.width,height:packet.height,videoGeneration:packet.videoGeneration,firstSourceMs:format?.videoGeneration===packet.videoGeneration?format.firstSourceMs:packet.frames[0].timestampMs};decoder.push(packet)}
      else{decoder.reset();last=-Infinity;clearTimeout(timer);timer=undefined;show(false);clearFrame()}
    })
    return ()=>{unsubscribe();clearTimeout(timer);decoder.dispose();lastFrame.current=null;canvasNode.style.opacity='0';gateOverlay();callbacks.current.onFrame?.(null);callbacks.current.onPlaying(false)}
  },[bus,cameraId,generation])
  return <><canvas ref={canvas} aria-hidden style={{position:'absolute',inset:0,width:'100%',height:'100%',objectFit:'contain',background:'#000',opacity:0,pointerEvents:'none'}}/><div ref={overlay} className="cm-native-overlay" aria-hidden style={{position:'absolute',inset:0,pointerEvents:'none',visibility:'hidden'}}>{children}</div></>
}
