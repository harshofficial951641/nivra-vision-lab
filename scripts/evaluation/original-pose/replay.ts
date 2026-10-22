import { ConflictEngine as OriginalEngine } from '../../src/lib/originalConflictEngine'
import { ConflictEngine as CurrentEngine } from '../../src/lib/conflictEngine'
const state = (window as any).__poseReplay = {done:false,error:null,runs:[] as any[],progress:''}
const publish = () => { document.getElementById('state')!.textContent = state.progress }
async function runCase(clip:any) {
  const worker = new Worker(new URL('../../src/workers/vision.worker.ts',import.meta.url),{type:'module'})
  let pending:any = null
  const request = (message:any,transfer:Transferable[] = []) => new Promise<any>((resolve,reject) => {
    const timer = setTimeout(() => reject(new Error('Worker timeout')),60000)
    pending = (data:any) => {
      clearTimeout(timer)
      if (data.type === 'error') reject(new Error(data.message))
      else resolve(data)
    }
    worker.postMessage(message,transfer)
  })
  worker.onmessage = ({data}) => pending?.(data)
  worker.onerror = e => pending?.({type:'error',message:e.message})
  const original = new OriginalEngine(),current = new CurrentEngine()
  const rows:any[] = []
  try {
    const ready = await request({type:'init',task:'pose',modelPath:'/models/pose_landmarker_full.task',wasmRoot:'/__nivra_wasm',maxPoses:4,poseConfidence:.5,objectConfidence:.35,poseDelegate:'CPU',portraitMultiPerson:false,personProposalPose:false})
    const began = performance.now()
    let previous = -Infinity
    for(const frame of clip.frames) {
      if(frame.timestampMs - previous < 50 - .001) continue
      previous = frame.timestampMs
      const response = await fetch('../pose-two-clip/' + frame.file)
      if(!response.ok) throw new Error('Missing private frame')
      const bitmap = await createImageBitmap(await response.blob())
      const started = performance.now()
      const data = await request({type:'frame',bitmap,timestampMs:frame.timestampMs},[bitmap])
      if(data.type !== 'pose-result' || data.timestampMs !== frame.timestampMs) throw new Error('Mismatched source response')
      const a = original.update(frame.timestampMs,data.poses,clip.width/clip.height)
      const b = current.update(frame.timestampMs,data.poses,clip.width/clip.height)
      rows.push({timestampMs:frame.timestampMs,file:frame.file,poseCount:data.poses.length,landmarks:data.poses,inferenceMs:data.inferenceMs,elapsedMs:performance.now()-started,original:a,current:b})
      state.progress = `${clip.clip}: ${rows.length} unique frames (${ready.delegate})`;publish()
    }
    return {clip:clip.clip,delegate:ready.delegate,minimumSourceIntervalMs:50,sourceWidth:clip.width,sourceHeight:clip.height,wallElapsedMs:performance.now()-began,rows}
  } finally {worker.terminate()}
}
async function main() {
  const clips = await (await fetch('../pose-two-clip/frames.json')).json()
  for(const clip of clips) state.runs.push(await runCase(clip))
  state.done = true;publish()
}
main().catch(error => {state.error = String(error);publish()})
