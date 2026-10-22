import { describe, expect, it } from 'vitest'
import { NativePoseHistory, nativeOverlayAligned } from './nativeTracking'
import type { WallCamera } from './model'
import type { NativeRenderedFrame } from '../classroom/nativeVideo'
const frame:NativeRenderedFrame={timestampMs:5000,width:1280,height:720,renderedAt:100000,generation:'g',videoGeneration:'v'}
const camera:WallCamera={id:'c',label:'CAM-1',name:'Entrance',floorId:null,slot:null,status:'live',sample:false,image:'blob:jpeg',people:1,fps:40,generation:'g',compute:'native',analysis:'current',deviceStatus:{state:'ready',delegate:'iOS',detail:'Phone detection'},result:{timestampMs:5000,evidenceTimestampMs:5000,inferenceMs:100},preview:{timestampMs:4000,width:960,height:540,generation:'g',received:100000}}
describe('native source-aligned markings',()=>{
  it('allows normalized720p skeletons over the exact decoded source despite a differently timed960p JPEG',()=>{
    expect(nativeOverlayAligned(camera,frame,frame,100000)).toBe(true)
    expect(nativeOverlayAligned(camera,{...frame,timestampMs:5180},frame,100000)).toBe(true)
    expect(nativeOverlayAligned(camera,{...frame,timestampMs:5181},frame,100000)).toBe(false)
    expect(nativeOverlayAligned(camera,{...frame,timestampMs:4819},frame,100000)).toBe(false)
  })
  it('requires matching portrait orientation and matching decoded overlay geometry',()=>{
    const portrait={...frame,width:720,height:1280}
    expect(nativeOverlayAligned({...camera,preview:{...camera.preview,width:540,height:960}},portrait,portrait,100000)).toBe(true)
    expect(nativeOverlayAligned(camera,portrait,portrait,100000)).toBe(false)
    expect(nativeOverlayAligned({...camera,preview:{...camera.preview,width:540,height:960}},portrait,frame,100000)).toBe(false)
    expect(nativeOverlayAligned(camera,{...frame,videoGeneration:'rotated'},frame,100000)).toBe(false)
    const restarted={...frame,firstSourceMs:5010,timestampMs:5020}
    expect(nativeOverlayAligned(camera,restarted,restarted,100000)).toBe(false)
  })
  it('hides stale, slow, unavailable or revoked analysis instead of borrowing JPEG alignment',()=>{
    expect(nativeOverlayAligned(camera,frame,frame,100501)).toBe(false)
    expect(nativeOverlayAligned({...camera,result:{...camera.result!,inferenceMs:1201}},frame,frame,100000)).toBe(false)
    expect(nativeOverlayAligned({...camera,analysis:'waiting'},frame,frame,100000)).toBe(false)
    expect(nativeOverlayAligned({...camera,deviceStatus:{state:'error',delegate:null,detail:'Unavailable'}},frame,frame,100000)).toBe(false)
    expect(nativeOverlayAligned({...camera,generation:'other'},frame,frame,100000)).toBe(false)
    expect(nativeOverlayAligned(camera,frame,null,100000)).toBe(false)
    expect(nativeOverlayAligned(camera,frame,{...frame,generation:'old-session'},100000)).toBe(false)
    expect(nativeOverlayAligned({...camera,preview:undefined},frame,frame,100000)).toBe(false)
  })
})

describe('bounded native pose report history',()=>{
  it('selects actual750ms older reports for rendered pixels and keeps strict180ms matching',()=>{
    const history=new NativePoseHistory()
    for(const timestampMs of [4000,4250,4500,4750,5000])history.add({...camera,result:{...camera.result!,timestampMs}},99000+(timestampMs-4000))
    expect(history.select(camera,{...frame,timestampMs:4250},100000)?.timestampMs).toBe(4250)
    expect(history.select(camera,{...frame,timestampMs:4180},100000)?.timestampMs).toBe(4250)
    expect(history.select(camera,{...frame,timestampMs:3819},100000)).toBeNull()
    const selected=history.select(camera,{...frame,timestampMs:4250},100000)
    expect(nativeOverlayAligned({...camera,result:selected},{...frame,timestampMs:4250},frame,100000)).toBe(true)
  })
  it('bounds report count/source span/wall age and rejects previous camera, stream and rotation observations',()=>{
    const history=new NativePoseHistory()
    for(let i=0;i<50;i++)history.add({...camera,result:{...camera.result!,timestampMs:1000+i*100}},100000+i*100)
    expect(history.size).toBe(20)
    expect(history.select(camera,{...frame,timestampMs:1000},105000)).toBeNull()
    expect(history.select(camera,{...frame,timestampMs:5000,firstSourceMs:5100},105000)).toBeNull()
    expect(history.select({...camera,id:'other'},frame,105000)).toBeNull()
    expect(history.select({...camera,generation:'other'},frame,105000)).toBeNull()
    history.add({...camera,generation:'next',result:{...camera.result!,timestampMs:6000}},105000)
    expect(history.size).toBe(1)
    expect(history.select(camera,frame,105000)).toBeNull()
    history.clear();expect(history.size).toBe(0)
  })
  it('does not rejuvenate repeated snapshots or draw history after current analysis becomes unhealthy',()=>{
    const history=new NativePoseHistory()
    history.add(camera,100000);history.add(camera,103999)
    expect(history.select(camera,frame,104001)).toBeNull()
    history.add(camera,104002);history.add(camera,104003)
    expect(history.select(camera,frame,104003)).toBeNull()
    expect(history.select({...camera,deviceStatus:{state:'error',delegate:null,detail:'Unavailable'}},frame,104002)).toBeNull()
    expect(history.select({...camera,analysis:'waiting'},frame,104002)).toBeNull()
  })
})
