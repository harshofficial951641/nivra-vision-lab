import { act, cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { NativeVideo } from './NativeVideoCanvas'
import { NativeVideoBus } from './nativeVideo'
const { state }=vi.hoisted(()=>({state:{draw:null as ((timestamp:number)=>void)|null,reset:vi.fn(),dispose:vi.fn()}}))
vi.mock('./nativeVideo',async original=>({...await original<typeof import('./nativeVideo')>(),NativeVideoDecoder:class { constructor(canvas:HTMLCanvasElement,draw:(timestamp:number)=>void){canvas.width=1280;canvas.height=720;state.draw=draw}push=vi.fn();reset=state.reset;dispose=state.dispose}}))
afterEach(()=>{cleanup();vi.clearAllMocks();vi.unstubAllGlobals();vi.useRealTimers();state.draw=null})
describe('native canvas fallback lifecycle',()=>{
  it('keeps JPEG visible when WebCodecs is unsupported',()=>{
    vi.stubGlobal('VideoDecoder',undefined)
    const playing=vi.fn(),view=render(<NativeVideo bus={new NativeVideoBus()} cameraId="c" generation="g" onPlaying={playing}/>)
    expect(view.container.querySelector('canvas')).toHaveStyle({opacity:'0'})
    expect(state.draw).toBeNull();expect(playing).not.toHaveBeenCalled()
  })
  it('changes React visibility only on playback transitions, falls back when stale and disposes on unmount',async()=>{
    vi.useFakeTimers();vi.stubGlobal('VideoDecoder',class {})
    const bus=new NativeVideoBus(),playing=vi.fn()
    bus.retain(new Map([['c','g']]))
    const view=render(<NativeVideo bus={bus} cameraId="c" generation="g" onPlaying={playing}/>)
    act(()=>{for(let i=0;i<40;i++)state.draw!(i*25)})
    expect(playing).toHaveBeenCalledExactlyOnceWith(true)
    expect(view.container.querySelector('canvas')).toHaveStyle({opacity:'1'})
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000)})
    expect(playing).toHaveBeenLastCalledWith(false)
    act(()=>state.draw!(2000));expect(playing).toHaveBeenLastCalledWith(true)
    act(()=>bus.clear());expect(playing).toHaveBeenLastCalledWith(false)
    expect(state.reset).toHaveBeenCalledOnce()
    view.unmount();expect(state.dispose).toHaveBeenCalledOnce();expect(vi.getTimerCount()).toBe(0)
  })
  it('samples source metadata at10Hz while hiding markings on every mismatched actual frame',async()=>{
    vi.useFakeTimers();vi.setSystemTime(100000);vi.stubGlobal('VideoDecoder',class {})
    const bus=new NativeVideoBus(),playing=vi.fn(),updates:{timestampMs:number;at:number}[]=[]
    bus.retain(new Map([['c','g']]))
    const onFrame=vi.fn(frame=>{if(frame)updates.push({timestampMs:frame.timestampMs,at:performance.now()})})
    const view=render(<NativeVideo bus={bus} cameraId="c" generation="g" onPlaying={playing} onFrame={onFrame} overlayMatches={frame=>Math.abs(frame.timestampMs-1000)<=180}><span>Real skeleton</span></NativeVideo>)
    act(()=>bus.publish({cameraId:'c',generation:'g',videoGeneration:'v',width:1280,height:720,codec:'avc1.42001f',description:new Uint8Array(7),frames:[{sequence:1,timestampMs:1000,keyframe:true,data:new Uint8Array(6)}]}))
    act(()=>state.draw!(1000))
    const layer=view.container.querySelector('.cm-native-overlay')!
    expect(layer).toHaveStyle({visibility:'visible'})
    for(let i=1;i<40;i++){
      await act(async()=>{await vi.advanceTimersByTimeAsync(25);state.draw!(1000+i*25)})
      if(i===8)expect(layer).toHaveStyle({visibility:'hidden'})
    }
    expect(updates).toHaveLength(10)
    expect(updates.every((update,i)=>i===0||update.at-updates[i-1].at>=100)).toBe(true)
    expect(onFrame).toHaveBeenCalledWith(expect.objectContaining({width:1280,height:720,generation:'g',videoGeneration:'v'}))
    expect(playing).toHaveBeenCalledExactlyOnceWith(true)
    act(()=>bus.clear())
    expect(layer).toHaveStyle({visibility:'hidden'})
    expect(onFrame).toHaveBeenLastCalledWith(null)
    view.unmount();expect(vi.getTimerCount()).toBe(0)
  })

})
