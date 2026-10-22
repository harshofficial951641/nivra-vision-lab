import { afterEach, describe, expect, it, vi } from 'vitest'
import { NativeVideoBus, NativeVideoDecoder, nativeVideoPacket } from './nativeVideo'
const description=btoa(String.fromCharCode(1,66,0,31,255,225,0))
function wire(count=1,overrides:Record<string,unknown>={}) {
  const payload=new Uint8Array(count*6)
  const frames=Array.from({length:count},(_,i)=>{payload.set([0,0,0,2,i===0?0x65:0x41,1],i*6);return {sequence:i,timestampMs:100+i*25,keyframe:i===0,offset:i*6,length:6}})
  const header=new TextEncoder().encode(JSON.stringify({encoding:'h264',cameraId:'c',generation:'g',videoGeneration:'v',width:1280,height:720,codec:'avc1.42001f',description,frames,...overrides}))
  const bytes=new Uint8Array(4+header.length+payload.length)
  new DataView(bytes.buffer).setUint32(0,header.length,true);bytes.set(header,4);bytes.set(payload,4+header.length)
  return bytes.buffer
}
const packet=(count=1)=>nativeVideoPacket(wire(count))!
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks()})
describe('bounded native packets',()=>{
  it('parses an initial90-frame GOP with AVCC slices and preserves source timestamps',()=>{
    const result=nativeVideoPacket(wire(90))!
    expect(result.frames).toHaveLength(90)
    expect(result.frames[1]).toMatchObject({sequence:1,timestampMs:125,keyframe:false})
    expect([...result.frames[0].data]).toEqual([0,0,0,2,101,1])
    expect(result.videoGeneration).toBe('v')
  })
  it('rejects excessive batches, malformed offsets/NAL lengths, invalid config and timestamps',()=>{
    expect(nativeVideoPacket(wire(91))).toBeNull()
    expect(nativeVideoPacket(new ArrayBuffer(3))).toBeNull()
    expect(nativeVideoPacket(wire(1,{description:'not-base64'}))).toBeNull()
    expect(nativeVideoPacket(wire(1,{frames:[{sequence:0,timestampMs:100,keyframe:true,offset:1,length:5}]}))).toBeNull()
    expect(nativeVideoPacket(wire(1,{frames:[{sequence:0,timestampMs:-1,keyframe:true,offset:0,length:6}]}))).toBeNull()
    const broken=wire()
    new Uint8Array(broken)[broken.byteLength-3]=50
    expect(nativeVideoPacket(broken)).toBeNull()
    expect(nativeVideoPacket(new ArrayBuffer(2*1024*1024+24581))).toBeNull()
  })
})
describe('workspace scoped video bus',()=>{
  it('isolates subscriptions, filters duplicate frames, and clears camera/generation state',()=>{
    const a=new NativeVideoBus(),b=new NativeVideoBus(),received=vi.fn(),other=vi.fn()
    a.retain(new Map([['c','g']]));b.retain(new Map([['c','g']]))
    a.subscribe('c','g',received);b.subscribe('c','g',other)
    a.publish(packet());a.publish(packet())
    expect(received).toHaveBeenCalledOnce();expect(other).not.toHaveBeenCalled()
    a.retain(new Map([['c','next']]))
    expect(received).toHaveBeenLastCalledWith(null)
    a.publish(packet());expect(received).toHaveBeenCalledTimes(2)
    a.clear();expect(received).toHaveBeenLastCalledWith(null)
  })
  it('accepts native encoder sequence restarts only with a new videoGeneration',()=>{
    const bus=new NativeVideoBus(),received=vi.fn()
    bus.retain(new Map([['c','g']]));bus.subscribe('c','g',received)
    bus.publish(packet(3));bus.publish(packet())
    expect(received).toHaveBeenCalledOnce()
    bus.publish({...packet(),videoGeneration:'new-encoder'})
    expect(received).toHaveBeenCalledTimes(2)
  })
})
function decoderHarness() {
  const decoders:FakeDecoder[]=[],outputs:{close:ReturnType<typeof vi.fn>}[]=[]
  class FakeDecoder {
    decodeQueueSize=0
    close=vi.fn();configure=vi.fn()
    output:VideoFrameOutputCallback
    error:VideoDecoderInit['error']
    constructor(init:VideoDecoderInit){this.output=init.output;this.error=init.error;decoders.push(this)}
    decode=vi.fn((chunk:EncodedVideoChunk)=>{
      const frame={timestamp:chunk.timestamp,displayWidth:1280,displayHeight:720,close:vi.fn()}
      outputs.push(frame);this.output(frame as unknown as VideoFrame)
    })
  }
  class Chunk {timestamp:number;type:string;constructor(init:EncodedVideoChunkInit){this.timestamp=init.timestamp;this.type=init.type}}
  vi.stubGlobal('VideoDecoder',FakeDecoder);vi.stubGlobal('EncodedVideoChunk',Chunk)
  const drawImage=vi.fn(),canvas={width:0,height:0,getContext:()=>({drawImage})} as unknown as HTMLCanvasElement
  const drawn=vi.fn(),decoder=new NativeVideoDecoder(canvas,drawn)
  return {decoder,decoders,outputs,drawImage,drawn,canvas}
}
describe('bounded native playback',()=>{
  it('draws real decoded frames after the bounded playout delay and closes each frame, without interpolation',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness();h.decoder.push(packet(3))
    expect(h.drawImage).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(699);expect(h.drawImage).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(52)
    expect(h.drawImage).toHaveBeenCalledTimes(3)
    expect(h.drawn.mock.calls.map(call=>call[0])).toEqual([100,125,150])
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
    h.decoder.dispose()
  })
  it('drops gapped deltas, resumes on a keyframe and resets on encoder generation changes',()=>{
    vi.useFakeTimers()
    const h=decoderHarness();h.decoder.push(packet())
    const next={...packet(),frames:[{...packet().frames[0],sequence:3,timestampMs:175,keyframe:false}]}
    h.decoder.push(next)
    expect(h.decoders[0].decode).toHaveBeenCalledOnce();expect(h.decoders[0].close).toHaveBeenCalledOnce()
    h.decoder.push({...next,frames:[{...next.frames[0],sequence:4,timestampMs:200,keyframe:true}]})
    expect(h.decoders).toHaveLength(2)
    h.decoder.push({...packet(),videoGeneration:'orientation-change'})
    expect(h.decoders).toHaveLength(3)
    expect(h.outputs.slice(0,2).every(frame=>frame.close.mock.calls.length===1)).toBe(true)
    h.decoder.dispose();expect(h.outputs.at(-1)!.close).toHaveBeenCalledOnce()
  })
  it('decodes a bounded initial GOP while discarding old output rather than starving before the next IDR',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness();h.decoder.push(packet(90))
    expect(h.decoders[0].decode).toHaveBeenCalledTimes(90)
    expect(h.outputs.filter(frame=>frame.close.mock.calls.length===0).length).toBeLessThanOrEqual(40)
    await vi.advanceTimersByTimeAsync(751)
    expect(h.drawn).toHaveBeenLastCalledWith(2325)
    expect(h.drawn.mock.calls.length).toBeGreaterThan(0)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })
  it('bounds sustained decode backlog after playback starts and recovers only on a new keyframe',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness();h.decoder.push(packet())
    await vi.advanceTimersByTimeAsync(751)
    h.decoders[0].decodeQueueSize=90
    const frame=packet().frames[0]
    h.decoder.push({...packet(),frames:[{...frame,sequence:1,timestampMs:125,keyframe:false}]})
    expect(h.decoders[0].close).toHaveBeenCalledOnce()
    h.decoder.push({...packet(),frames:[{...frame,sequence:2,timestampMs:150,keyframe:false}]})
    expect(h.decoders).toHaveLength(1)
    h.decoder.push({...packet(),frames:[{...frame,sequence:3,timestampMs:175,keyframe:true}]})
    expect(h.decoders).toHaveLength(2)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
  })
  it('recovers from a corrupt decode at the next IDR, caps repeated failures and retries a new encoder generation',()=>{
    vi.useFakeTimers()
    const h=decoderHarness(),base=packet()
    for(let i=0;i<3;i++){
      h.decoder.push({...base,frames:[{...base.frames[0],sequence:i,timestampMs:100+i*25}]})
      expect(h.decoders).toHaveLength(i+1)
      h.decoders[i].error(new DOMException('Corrupt AVC','EncodingError'))
    }
    h.decoder.push({...base,frames:[{...base.frames[0],sequence:3,timestampMs:175}]})
    expect(h.decoders).toHaveLength(3)
    h.decoder.push({...base,videoGeneration:'fresh-encoder'})
    expect(h.decoders).toHaveLength(4)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
  })

  it('plays40fps source observations through600ms network bursts without decoder starvation',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness(),base=packet(),source=base.frames[0]
    const send=(from:number,to:number)=>h.decoder.push({...base,frames:Array.from({length:to-from},(_,i)=>{const sequence=from+i;return {...source,sequence,timestampMs:100+sequence*25,keyframe:sequence%40===0}})})
    send(0,1)
    let elapsed=0,sequence=1
    for(const interval of [100,100,600,100,300,600,100,100,600,100,300,600]){
      elapsed+=interval
      await vi.advanceTimersByTimeAsync(interval)
      const next=Math.floor(elapsed/25)+1
      send(sequence,next);sequence=next
    }
    await vi.advanceTimersByTimeAsync(751)
    expect(h.decoders).toHaveLength(1)
    expect(h.drawn).toHaveBeenCalledTimes(sequence)
    expect(h.drawn.mock.calls.map(call=>call[0])).toEqual(Array.from({length:sequence},(_,i)=>100+i*25))
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
  })

  it('re-anchors presentation after a persistent network delay shift without losing the valid codec chain',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness();h.decoder.push(packet())
    await vi.advanceTimersByTimeAsync(751)
    await vi.advanceTimersByTimeAsync(1500)
    const delayed=packet(62)
    h.decoder.push({...delayed,frames:delayed.frames.slice(1)})
    await vi.advanceTimersByTimeAsync(751)
    expect(h.decoders).toHaveLength(1)
    expect(h.drawn).toHaveBeenLastCalledWith(1625)
    const read=(h.canvas as HTMLCanvasElement & {__nivraVideoMetrics:()=>Record<string,number>}).__nivraVideoMetrics
    expect(read().clockRebases).toBe(1)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
  })

  it('catches up to the newest due observation after delayed presentation without drawing a future frame',async()=>{
    vi.useFakeTimers()
    let clock=0
    vi.spyOn(performance,'now').mockImplementation(()=>clock)
    const h=decoderHarness(),base=packet(),source=base.frames[0]
    h.decoder.push(base)
    // Decoder output continues while the presentation callback is delayed.
    for(let sequence=1;sequence<=80;sequence++){
      clock=sequence*25
      h.decoder.push({...base,frames:[{...source,sequence,timestampMs:100+sequence*25,keyframe:false}]})
    }
    expect(h.drawn).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(750)
    expect(h.drawn).toHaveBeenLastCalledWith(1350)
    expect(h.drawn).toHaveBeenCalledOnce()
    clock=2025
    h.decoder.push({...base,frames:[{...source,sequence:81,timestampMs:2125,keyframe:false}]})
    await vi.advanceTimersByTimeAsync(25)
    expect(h.drawn).toHaveBeenLastCalledWith(1375)
    expect(h.drawn).toHaveBeenCalledTimes(2)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('bounds source clock drift without starving continuous playback or resetting the codec',async()=>{
    vi.useFakeTimers()
    const h=decoderHarness(),base=packet(),source=base.frames[0]
    let drewFuture=false
    const read=()=>(h.canvas as HTMLCanvasElement & {__nivraVideoMetrics:()=>Record<string,number>}).__nivraVideoMetrics()
    h.drawn.mockImplementation(timestamp=>{const m=read();if(m.baseWallMs+timestamp-m.baseSourceMs>performance.now()+1)drewFuture=true})
    h.decoder.push(base)
    for(let sequence=1;sequence<=800;sequence++){
      await vi.advanceTimersByTimeAsync(24)
      h.decoder.push({...base,frames:[{...source,sequence,timestampMs:100+sequence*25,keyframe:sequence%40===0}]})
      expect(read().bufferedFrames).toBeLessThanOrEqual(40)
    }
    expect(drewFuture).toBe(false)
    const metrics=(h.canvas as HTMLCanvasElement & {__nivraVideoMetrics:()=>Record<string,number>}).__nivraVideoMetrics()
    expect(metrics.clockCorrections).toBeGreaterThan(0)
    expect(metrics.tailDueInMs).toBeLessThanOrEqual(851)
    expect(h.drawn.mock.calls.length).toBeGreaterThan(700)
    expect(h.decoders).toHaveLength(1)
    h.decoder.dispose()
    expect(h.outputs.every(frame=>frame.close.mock.calls.length===1)).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

})
