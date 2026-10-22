import type { NativeRenderedFrame } from '../classroom/nativeVideo'
import type { WallCamera } from './model'
/** Native pixels and JPEG overlays share normalized coordinates only with matching orientation. */
export function nativeOverlayAligned(camera:WallCamera,frame:NativeRenderedFrame,overlayFrame:NativeRenderedFrame|null,now:number) {
  const result=camera.result,preview=camera.preview
  if(camera.sample || camera.status!=='live' || camera.analysis!=='current' || !result || !overlayFrame || frame.generation!==camera.generation || overlayFrame.generation!==frame.generation || frame.videoGeneration!==overlayFrame.videoGeneration || frame.width!==overlayFrame.width || frame.height!==overlayFrame.height) return false
  if(frame.firstSourceMs!==undefined && (!Number.isFinite(frame.firstSourceMs) || result.timestampMs<frame.firstSourceMs)) return false
  if(camera.compute!=='pc' && camera.deviceStatus?.state!=='ready') return false
  if(![frame.timestampMs,frame.renderedAt,frame.width,frame.height,result.timestampMs,result.inferenceMs,now].every(Number.isFinite) || frame.width<=0 || frame.height<=0 || result.inferenceMs<0 || result.inferenceMs>1200 || now-frame.renderedAt<0 || now-frame.renderedAt>500 || Math.abs(frame.timestampMs-result.timestampMs)>180) return false
  if(!preview?.width || !preview.height || !Number.isFinite(preview.width) || !Number.isFinite(preview.height) || preview.width<=0 || preview.height<=0 || preview.generation!==frame.generation) return false
  // Encoding may round one edge by a pixel; portrait/landscape flips never fit.
  return Math.abs(frame.width/frame.height-preview.width/preview.height)<=.005
}
