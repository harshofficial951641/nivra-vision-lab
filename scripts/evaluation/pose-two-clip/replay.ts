import { DeviceAnalysis } from '../../src/classroom/deviceAnalysis'
import { ConflictEngine } from '../../src/lib/conflictEngine'
const state=(window as any).__poseReplay={done:false,error:null,runs:[] as any[],progress:''}
const publish=()=>{document.getElementById('state')!.textContent=JSON.stringify(state,null,2)}
async function runCase(clip:any,minimumMs:number) {
 const worker=new Worker(new URL('../../src/workers/vision.worker.ts',import.meta.url),{type:'module'})
 let pending:any=null
 const request=(message:any,transfer:Transferable[]=[])=>new Promise<any>((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('worker timeout')),30000)
  pending=(data:any)=>{clearTimeout(timer);if(data.type==='error')reject(new Error(data.message));else resolve(data)}
  worker.postMessage(message,transfer)
 })
 worker.onmessage=({data})=>pending?.(data)
 worker.onerror=(e)=>pending?.({type:'error',message:e.message})
 const analysis=new DeviceAnalysis(),original=new ConflictEngine()
 const rows:any[]=[]
 try {
 const ready=await request({type:'init',task:'pose',modelPath:'/models/pose_landmarker_full.task',wasmRoot:'/__nivra_wasm',maxPoses:4,poseConfidence:.5,objectConfidence:.35,poseDelegate:'GPU',portraitMultiPerson:false,personProposalPose:false})
 let previous=-Infinity
 const began=performance.now()
 for(const frame of clip.frames){
  if(frame.timestampMs-previous<minimumMs-.001)continue
  previous=frame.timestampMs
  const response=await fetch('./'+frame.file);const bitmap=await createImageBitmap(await response.blob())
  const started=performance.now()
  const data=await request({type:'frame',bitmap,timestampMs:frame.timestampMs},[bitmap])
  if(data.type!=='pose-result'||data.timestampMs!==frame.timestampMs)throw new Error('Mismatched source response')
  const current=analysis.update(frame.timestampMs,data.inferenceMs,data.poses,clip.width/clip.height,ready.delegate)
  const legacy=original.update(frame.timestampMs,data.poses,clip.width/clip.height)
  rows.push({timestampMs:frame.timestampMs,file:frame.file,poses:data.poses.length,inferenceMs:data.inferenceMs,elapsedMs:performance.now()-started,device:{people:current.usablePeople,status:current.conflict.status,explanation:current.conflict.explanation,events:current.events},original:{people:legacy.people,status:legacy.status,explanation:legacy.explanation,diagnostics:legacy.diagnostics,events:legacy.events}})
  state.progress=`${clip.clip} ${minimumMs}ms ${rows.length} unique frames`;publish()
 }
 return {clip:clip.clip,minimumSourceIntervalMs:minimumMs,delegate:ready.delegate,model:'pose_landmarker_full.task',numPoses:4,wallElapsedMs:performance.now()-began,rows}
 } finally {worker.terminate()}
}
async function main(){
 const clips=await(await fetch('./frames.json')).json()
 for(const interval of [200,50])for(const clip of clips){state.runs.push(await runCase(clip,interval));publish()}
 state.done=true;publish()
}
main().catch(error=>{state.error=String(error);publish()})
