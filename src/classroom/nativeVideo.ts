export type NativeRenderedFrame = { timestampMs:number; width:number; height:number; renderedAt:number; firstSourceMs?:number; generation:string; videoGeneration:string }

/** Authenticated native video packets use source PTS, never wall-clock timestamps. */
export type NativeFrame = { sequence:number; timestampMs:number; keyframe:boolean; data:Uint8Array }
export type NativePacket = { cameraId:string; generation:string; videoGeneration:string; width:number; height:number; codec:string; description:Uint8Array; frames:NativeFrame[] }
const MAX_BYTES = 2 * 1024 * 1024
const integer = (n:unknown, min:number, max:number):n is number => typeof n === 'number' && Number.isSafeInteger(n) && n >= min && n <= max
export function nativeVideoPacket(bytes:ArrayBuffer):NativePacket | null {
  try {
    if(bytes.byteLength < 5 || bytes.byteLength > MAX_BYTES + 24580) return null
    const size=new DataView(bytes).getUint32(0,true)
    if(size < 2 || size > 24576 || size+4 >= bytes.byteLength) return null
    const meta=JSON.parse(new TextDecoder().decode(new Uint8Array(bytes,4,size)))
    if(meta.encoding !== 'h264' || typeof meta.cameraId !== 'string' || !meta.cameraId || meta.cameraId.length>100 || typeof meta.generation !== 'string' || !meta.generation || meta.generation.length>100 || !integer(meta.width,1,4096) || !integer(meta.height,1,4096) || typeof meta.codec !== 'string' || !/^avc[13]\.[a-f0-9]{6}$/i.test(meta.codec) || typeof meta.description !== 'string' || meta.description.length>5500 || !Array.isArray(meta.frames) || !meta.frames.length || meta.frames.length>90) return null
    if(meta.videoGeneration !== undefined && (typeof meta.videoGeneration !== 'string' || !meta.videoGeneration || meta.videoGeneration.length>100)) return null
    const description=Uint8Array.from(atob(meta.description),char=>char.charCodeAt(0))
    if(description.length<7 || description.length>4096 || description[0]!==1) return null
    const nalSize=(description[4]&3)+1
    if(nalSize===3) return null
    const payload=new Uint8Array(bytes,4+size)
    if(payload.byteLength>MAX_BYTES) return null
    const frames:NativeFrame[]=[]
    let end=0,lastSequence=-1,lastTimestamp=-1
    for(const frame of meta.frames) {
      if(!integer(frame.sequence,0,Number.MAX_SAFE_INTEGER) || frame.sequence<=lastSequence || typeof frame.timestampMs!=='number' || !Number.isFinite(frame.timestampMs) || frame.timestampMs<0 || frame.timestampMs<=lastTimestamp || typeof frame.keyframe!=='boolean' || !integer(frame.offset,0,payload.length) || frame.offset!==end || !integer(frame.length,1,MAX_BYTES) || frame.offset+frame.length>payload.length) return null
      const data=payload.subarray(frame.offset,frame.offset+frame.length)
      let cursor=0,units=0
      while(cursor<data.length) {
        if(cursor+nalSize>data.length || ++units>512) return null
        let length=0
        for(let i=0;i<nalSize;i++) length=length*256+data[cursor+i]
        cursor+=nalSize
        if(!length || cursor+length>data.length) return null
        cursor+=length
      }
      frames.push({sequence:frame.sequence,timestampMs:frame.timestampMs,keyframe:frame.keyframe,data})
      end=frame.offset+frame.length;lastSequence=frame.sequence;lastTimestamp=frame.timestampMs
    }
    if(end!==payload.length) return null
    return {cameraId:meta.cameraId,generation:meta.generation,videoGeneration:meta.videoGeneration ?? meta.generation,width:meta.width,height:meta.height,codec:meta.codec,description,frames}
  } catch { return null }
}

type Listener=(packet:NativePacket|null)=>void
/** A hook-owned bus retains metadata only, never a global cache of camera footage. */
export class NativeVideoBus {
  private active=new Map<string,string>()
  private listeners=new Map<string,Set<Listener>>()
  private last=new Map<string,{sequence:number;videoGeneration:string}>()
  retain(active:Map<string,string|null|undefined>) {
    for(const [id,generation] of this.active) if(active.get(id)!==generation) {
      this.listeners.get(id)?.forEach(listener=>listener(null));this.last.delete(id)
    }
    this.active=new Map([...active].filter((entry):entry is [string,string]=>!!entry[1]))
  }
  publish(packet:NativePacket) {
    if(this.active.get(packet.cameraId)!==packet.generation) return
    const previous=this.last.get(packet.cameraId)
    const frames=packet.frames.filter(frame=>frame.sequence>(previous?.videoGeneration===packet.videoGeneration ? previous.sequence : -1))
    if(!frames.length) return
    this.last.set(packet.cameraId,{sequence:frames.at(-1)!.sequence,videoGeneration:packet.videoGeneration})
    this.listeners.get(packet.cameraId)?.forEach(listener=>listener({...packet,frames}))
  }
  subscribe(cameraId:string,generation:string,listener:Listener) {
    const scoped:Listener=packet=>listener(packet?.generation===generation ? packet : null)
    const listeners=this.listeners.get(cameraId) ?? new Set<Listener>()
    listeners.add(scoped);this.listeners.set(cameraId,listeners)
    return ()=>{listeners.delete(scoped);if(!listeners.size)this.listeners.delete(cameraId)}
  }
  clear() { this.listeners.forEach(listeners=>listeners.forEach(listener=>listener(null)));this.active.clear();this.last.clear() }
}

/** One bounded decoder per visible tile; dropped/gapped streams resume at an IDR. */
export class NativeVideoDecoder {
  private decoder:VideoDecoder|null=null
  private config=''
  private waitingKey=true
  private lastSequence=-1
  private lastTimestamp=-1
  private frames:{frame:VideoFrame;due:number}[]=[]
  private timer:ReturnType<typeof setTimeout>|undefined
  private latestInputTimestamp=-1
  private primed=false
  private baseSource=0
  private baseWall=0
  private disposed=false
  private failed=false
  private failures=0
  private epoch=0
  private canvas:HTMLCanvasElement
  private drawn:(timestampMs:number)=>void
  constructor(canvas:HTMLCanvasElement,drawn:(timestampMs:number)=>void) {this.canvas=canvas;this.drawn=drawn}
  push(packet:NativePacket) {
    if(this.disposed || typeof VideoDecoder==='undefined' || typeof EncodedVideoChunk==='undefined') return
    const config=`${packet.videoGeneration}:${packet.codec}:${Array.from(packet.description).join(',')}:${packet.width}x${packet.height}`
    if(this.config!==config) {this.reset();this.config=config;this.lastSequence=-1;this.lastTimestamp=-1;this.failures=0;this.failed=false}
    if(this.failed)return
    this.latestInputTimestamp=packet.frames.at(-1)!.timestampMs
    let start=0
    if(this.waitingKey) for(let i=packet.frames.length-1;i>=0;i--) if(packet.frames[i].keyframe){start=i;break}
    for(const frame of packet.frames.slice(start)) {
      if(frame.sequence<=this.lastSequence) continue
      if((this.lastSequence>=0 && frame.sequence!==this.lastSequence+1) || frame.timestampMs<=this.lastTimestamp) this.reset()
      this.lastSequence=frame.sequence;this.lastTimestamp=frame.timestampMs
      if(this.waitingKey && !frame.keyframe) continue
      if((this.decoder?.decodeQueueSize ?? 0)>=(this.primed?12:90)) {this.reset();if(!frame.keyframe)continue}
      try {
        if(!this.decoder) {
          const epoch=++this.epoch
          this.baseSource=this.latestInputTimestamp;this.baseWall=performance.now()+150
          this.decoder=new VideoDecoder({output:decoded=>{
            if(this.disposed || epoch!==this.epoch) {decoded.close();return}
            const timestamp=decoded.timestamp/1000
            if(timestamp<this.latestInputTimestamp-150){decoded.close();return}
            const due=this.baseWall+timestamp-this.baseSource
            if(due<performance.now()-150){decoded.close();return}
            if(this.frames.length>=8){this.frames.shift()!.frame.close();clearTimeout(this.timer);this.timer=undefined}
            this.frames.push({frame:decoded,due});this.schedule()
          },error:()=>{if(epoch===this.epoch)this.decodeFailed()}})
          this.decoder.configure({codec:packet.codec,description:packet.description as Uint8Array<ArrayBuffer>,hardwareAcceleration:'prefer-hardware',optimizeForLatency:true})
        }
        this.waitingKey=false
        this.decoder.decode(new EncodedVideoChunk({type:frame.keyframe?'key':'delta',timestamp:Math.round(frame.timestampMs*1000),data:frame.data as Uint8Array<ArrayBuffer>}))
      } catch {this.decodeFailed();return}
    }
  }
  private schedule() {
    if(this.timer!==undefined || !this.frames.length) return
    this.timer=setTimeout(()=>{
      this.timer=undefined
      const next=this.frames.shift()
      if(!next)return
      try {
        if(this.canvas.width!==next.frame.displayWidth)this.canvas.width=next.frame.displayWidth
        if(this.canvas.height!==next.frame.displayHeight)this.canvas.height=next.frame.displayHeight
        const context=this.canvas.getContext('2d')
        if(context){context.drawImage(next.frame,0,0);this.primed=true;this.failures=0;this.drawn(next.frame.timestamp/1000)}
      } catch {this.decodeFailed()} finally {next.frame.close()}
      this.schedule()
    },Math.max(0,this.frames[0].due-performance.now()))
  }
  private decodeFailed(){this.reset();this.failures++;this.failed=this.failures>=3}
  reset() {
    this.epoch++;clearTimeout(this.timer);this.timer=undefined
    for(const item of this.frames)item.frame.close()
    this.frames=[];this.baseWall=0;this.primed=false;this.waitingKey=true
    try {this.decoder?.close()} catch { /* Decoder can already be closed after an error. */ }
    this.decoder=null
  }
  dispose(){this.disposed=true;this.reset()}
}
