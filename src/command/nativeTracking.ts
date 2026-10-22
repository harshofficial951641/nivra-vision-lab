import type { NativeRenderedFrame } from '../classroom/nativeVideo'
import type { WallCamera } from './model'
/** Native pixels and JPEG overlays share normalized coordinates only with matching orientation. */
export function nativeOverlayAligned(camera:WallCamera,frame:NativeRenderedFrame,overlayFrame:NativeRenderedFrame|null,now:number) {
  const result=camera.result,preview=camera.preview
  if(camera.sample || camera.status!=='live' || camera.analysis!=='current' || !result || !overlayFrame || frame.generation!==camera.generation || overlayFrame.generation!==frame.generation || frame.videoGeneration!==overlayFrame.videoGeneration || frame.width!==overlayFrame.width || frame.height!==overlayFrame.height) return false
  if(frame.firstSourceMs!==undefined && (!Number.isFinite(frame.firstSourceMs) || frame.timestampMs<frame.firstSourceMs || result.timestampMs<frame.firstSourceMs)) return false
  if(camera.compute!=='pc' && camera.deviceStatus?.state!=='ready') return false
  if(![frame.timestampMs,frame.renderedAt,frame.width,frame.height,result.timestampMs,result.inferenceMs,now].every(Number.isFinite) || frame.width<=0 || frame.height<=0 || result.inferenceMs<0 || result.inferenceMs>1200 || now-frame.renderedAt<0 || now-frame.renderedAt>500 || Math.abs(frame.timestampMs-result.timestampMs)>180) return false
  if(!preview?.width || !preview.height || !Number.isFinite(preview.width) || !Number.isFinite(preview.height) || preview.width<=0 || preview.height<=0 || preview.generation!==frame.generation) return false
  // Encoding may round one edge by a pixel; portrait/landscape flips never fit.
  return Math.abs(frame.width/frame.height-preview.width/preview.height)<=.005
}

type PoseResult = NonNullable<WallCamera['result']>
/** Recent actual reports for delayed native pixels, scoped to one camera stream. */
export class NativePoseHistory {
  private cameraId:string|null=null
  private generation:string|null=null
  private reports:{result:PoseResult;received:number}[]=[]
  private newestSeen=-1
  get size(){return this.reports.length}
  clear(){this.cameraId=null;this.generation=null;this.reports=[];this.newestSeen=-1}
  add(camera:WallCamera,now:number) {
    if(!camera.generation || camera.status!=='live' || camera.sample){this.clear();return}
    if(this.cameraId!==camera.id || this.generation!==camera.generation){this.clear();this.cameraId=camera.id;this.generation=camera.generation}
    const result=camera.result
    if(!result || !Number.isFinite(result.timestampMs) || result.timestampMs<0 || !Number.isFinite(now))return
    // Repeated snapshots cannot make a frozen observation young again.
    if(result.timestampMs>this.newestSeen){this.newestSeen=result.timestampMs;this.reports.push({result,received:now})}
    const newest=this.newestSeen
    this.reports=this.reports.filter(item=>newest-item.result.timestampMs<=4000 && now-item.received<=4000)
      .sort((a,b)=>a.result.timestampMs-b.result.timestampMs).slice(-20)
  }
  select(camera:WallCamera,frame:NativeRenderedFrame,now:number):PoseResult|null {
    if(this.cameraId!==camera.id || this.generation!==camera.generation || frame.generation!==this.generation || camera.status!=='live' || camera.analysis!=='current' || !camera.result || (camera.compute!=='pc' && camera.deviceStatus?.state!=='ready'))return null
    if(frame.firstSourceMs!==undefined && frame.timestampMs<frame.firstSourceMs)return null
    let closest:PoseResult|null=null,distance=181
    for(const item of this.reports){
      const delta=Math.abs(item.result.timestampMs-frame.timestampMs)
      if(now-item.received<0 || now-item.received>4000 || (frame.firstSourceMs!==undefined && item.result.timestampMs<frame.firstSourceMs))continue
      if(delta<distance){distance=delta;closest=item.result}
    }
    return closest
  }
}
