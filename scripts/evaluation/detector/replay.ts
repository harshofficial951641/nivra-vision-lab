import { DeviceVision } from '../../../src/classroom/DeviceVision'
import { RTMO_T_MODEL } from '../../../src/classroom/CrowdPoseVision'
import type { DeviceResult, DeviceMotion, DeviceStatus } from '../../../src/classroom/deviceAnalysis'

// Instrument messages, not inference or decisions: the unchanged publisher client
// still owns capture, resizing, admission, worker configuration and alert delivery.
const NativeWorker = window.Worker
let active: { frames: any[]; requests: Map<Worker, Map<number, any>>; video: HTMLVideoElement } | null = null
class ObservedWorker extends NativeWorker {
  private lane: 'motion' | 'crowd' | null = null
  constructor(url: string | URL, options?: WorkerOptions) {
    super(url, options)
    this.addEventListener('message', ({data}) => {
      if (data.type === 'error') console.error('Worker failure: '+data.message)
      if (!active || !this.lane) return
      const result = data.type === 'pose-result' ? data : data.type === 'result' ? data.result : null
      if (!result) return
      const pending = active.requests.get(this)?.get(result.timestampMs)
      if (!pending) return
      active.requests.get(this)!.delete(result.timestampMs)
      active.frames.push({lane:this.lane, timestampMs:result.timestampMs, aspect:pending.aspect,
        inferenceMs:result.inferenceMs, completedSourceMs:active.video.currentTime * 1000,
        elapsedMs:performance.now()-pending.began, poses:result.poses, people:result.people,
        delegate:result.delegate ?? 'CPU'})
    })
  }
  postMessage(message: any, transfer: Transferable[]): void
  postMessage(message: any, options?: StructuredSerializeOptions): void
  postMessage(message: any, transfer?: Transferable[] | StructuredSerializeOptions) {
    if (message.type === 'init') this.lane = message.task === 'pose' ? 'motion' : message.model ? 'crowd' : null
    if (active && this.lane && message.type === 'frame') {
      let requests=active.requests.get(this)
      if (!requests) { requests=new Map(); active.requests.set(this,requests) }
      requests.set(message.timestampMs,{aspect:active.video.videoWidth/active.video.videoHeight,began:performance.now()})
    }
    if (Array.isArray(transfer)) super.postMessage(message,transfer)
    else super.postMessage(message,transfer)
  }
}
window.Worker=ObservedWorker
const wait = (ms:number) => new Promise(resolve=>setTimeout(resolve,ms))
const alerts = (report:DeviceResult|DeviceMotion) => report.events.map(event=>({
  id:event.id.slice(event.id.lastIndexOf('conflict-')), occurredAtMs:event.occurredAtMs, detail:event.detail,
}))

;(window as any).replayVideo = async (job:{id:string;url:string;experimentalProfile?:string|null}) => {
  const video=document.querySelector('video')!
  const state=document.getElementById('status')!
  video.src=job.url
  await new Promise<void>((resolve,reject)=>{
    video.onloadeddata=()=>resolve();video.onerror=()=>reject(new Error('Video decode failed: '+video.error?.code)); video.load()
  })
  const frames:any[]=[],liveAlerts:any[]=[],reports:any[]=[],statuses:any[]=[]
  active={frames,requests:new Map(),video}
  let motionReady=false,crowdReady=false,error:string|null=null
  const onStatus=(lane:string)=>(status:DeviceStatus)=>{
    statuses.push({lane,...status});
    if(status.state==='error')error=lane+': '+status.detail
    if(lane==='motion'&&status.state==='ready')motionReady=true
    // DeviceVision deliberately waits for its first crowd result to announce ready.
    if(lane==='crowd'&&status.detail.startsWith('Starting crowd detection.'))crowdReady=true
    if(status.detail.includes('unavailable'))error='Unexpected fallback: '+status.detail
  }
  const device=new DeviceVision(onStatus('crowd'),r=>{
    if(r.events.length&&!job.experimentalProfile)error='Observation lane emitted an alert'
    if(job.experimentalProfile)liveAlerts.push(...alerts(r))
    reports.push({lane:'crowd',timestampMs:r.timestampMs,observedPeople:r.observedPeople,usablePeople:r.usablePeople})
  },'full','crowd',r=>{liveAlerts.push(...alerts(r));reports.push({lane:'motion',timestampMs:r.timestampMs,usablePeople:r.usablePeople,observedPeople:r.observedPeople})},onStatus('motion'),RTMO_T_MODEL,{experimentalProfile:job.experimentalProfile??null})
  let callback=0
  try {
    device.start('CPU')
    const began=performance.now()
    while(!motionReady||!crowdReady){if(error)throw new Error(error);if(performance.now()-began>90000)throw new Error('Model initialization timeout');await wait(20)}
    const frame=(_now:number,metadata:VideoFrameCallbackMetadata)=>{
      void device.capture(video,metadata.mediaTime*1000)
      callback=video.requestVideoFrameCallback(frame)
    }
    callback=video.requestVideoFrameCallback(frame)
    const ended=new Promise<void>((resolve,reject)=>{video.onended=()=>resolve();video.onerror=()=>reject(new Error('Playback failed'))})
    const started=performance.now()
    await video.play()
    await Promise.race([ended,new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error('Playback deadline exceeded')),Math.ceil(video.duration*1000)+15000))])
    video.cancelVideoFrameCallback(callback)
    // Drain only in-flight real frames. No duplicated end frames or invented PTS.
    const drain=performance.now()
    while([...active.requests.values()].some(v=>v.size)){if(performance.now()-drain>11000)throw new Error('Worker drain timeout');await wait(10)}
    await wait(0)
    if(error)throw new Error(error)
    if(!frames.some(f=>f.lane==='motion')||!frames.some(f=>f.lane==='crowd'))throw new Error('A lane produced no frames')
    state.textContent=job.id+' complete'
    return {schemaVersion:1,id:job.id,sourceWidth:video.videoWidth,sourceHeight:video.videoHeight,
      durationMs:video.duration*1000,wallElapsedMs:performance.now()-started,protocol:'publisher-real-time-cpu-v1',
      frames:JSON.parse(JSON.stringify(frames)),liveAlerts,reports,statuses}
  } finally {video.pause();video.cancelVideoFrameCallback(callback);device.dispose();active=null;video.removeAttribute('src');video.load()}
}
;(window as any).detectorReady=true

