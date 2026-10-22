import type { VisionDelegate } from '../types/vision'
import type { CrowdPoseModel, CrowdPoseResult } from './crowdPoseGeometry'
export type { CrowdPoseModel, CrowdPoseResult } from './crowdPoseGeometry'
export const RTMO_T_MODEL: CrowdPoseModel = Object.freeze({modelPath:`${import.meta.env.BASE_URL}models/rtmo-t-body7-416-20aad6e2.onnx`,sha256:'20aad6e2e42359cac1c5b4a0b2da00e29bfe91a72a782fdcf287d273a04c1b24',inputSide:416,preferredDelegate:'CPU'})
type Reply={type:'ready';delegate:VisionDelegate}|{type:'result';result:CrowdPoseResult}|{type:'error';message:string}
/** One browser-only crowd graph, one observed image in flight, no frame queue. */
export class CrowdPoseVision {
  delegate:VisionDelegate='CPU'
  private worker:Worker|null=null
  private disposed=false
  private ready=false
  private inferred=false
  private initialization:Promise<void>|null=null
  private pending:{timestamp:number;resolve:(result:CrowdPoseResult)=>void;reject:(error:Error)=>void}|null=null
  private resolveReady:(()=>void)|null=null
  private rejectReady:((error:Error)=>void)|null=null
  private timer:ReturnType<typeof setTimeout>|undefined
  private model:CrowdPoseModel
  constructor(model:CrowdPoseModel){this.model=model}
  start():Promise<void>{
    if(this.disposed)return Promise.reject(new Error('Crowd detection stopped.'))
    if(this.initialization)return this.initialization
    this.initialization=new Promise((resolve,reject)=>{this.resolveReady=resolve;this.rejectReady=reject})
    try{
      if(!/^[a-f0-9]{64}$/.test(this.model.sha256)||![416,640].includes(this.model.inputSide))throw new Error('Crowd model has not been validated.')
      const worker=new Worker(new URL('../workers/crowdPose.worker.ts',import.meta.url),{type:'module'})
      this.worker=worker
      worker.onerror=()=>this.fail(new Error('Crowd detection worker failed.'))
      worker.onmessageerror=()=>this.fail(new Error('Crowd detection returned an unreadable result.'))
      worker.onmessage=({data}:MessageEvent<Reply>)=>{
        if(this.disposed||this.worker!==worker)return
        if(data.type==='error'){this.fail(new Error(data.message));return}
        if(data.type==='ready'){this.delegate=data.delegate??'CPU';clearTimeout(this.timer);this.ready=true;this.resolveReady?.();this.resolveReady=this.rejectReady=null}
        if(data.type==='result'&&data.result.timestampMs===this.pending?.timestamp){clearTimeout(this.timer);this.inferred=true;const pending=this.pending;this.pending=null;pending.resolve(data.result)}
      }
      this.timer=setTimeout(()=>this.fail(new Error('Crowd model loading timed out.')),30000)
      worker.postMessage({type:'init',model:this.model})
    }catch(error){this.fail(error instanceof Error?error:new Error('Crowd model unavailable.'))}
    return this.initialization
  }
  analyze(bitmap:ImageBitmap,timestampMs:number):Promise<CrowdPoseResult>{
    if(this.disposed||!this.ready||!this.worker||this.pending||!Number.isFinite(timestampMs)||timestampMs<0){bitmap.close();return Promise.reject(new Error('Crowd detection is not ready for a frame.'))}
    return new Promise((resolve,reject)=>{
      this.pending={timestamp:timestampMs,resolve,reject}
      this.timer=setTimeout(()=>this.fail(new Error(this.inferred?'Crowd inference exceeded three seconds.':'First crowd inference exceeded twelve seconds.')),this.inferred?3000:12000)
      try{this.worker!.postMessage({type:'frame',bitmap,timestampMs},[bitmap])}catch(error){bitmap.close();this.fail(error instanceof Error?error:new Error('Could not send the crowd frame.'))}
    })
  }
  private fail(error:Error){
    this.disposed=true;this.ready=false;clearTimeout(this.timer);this.worker?.terminate();this.worker=null
    this.rejectReady?.(error);this.resolveReady=this.rejectReady=null
    this.pending?.reject(error);this.pending=null
  }
  dispose(){this.fail(new Error('Crowd detection stopped.'))}
}
