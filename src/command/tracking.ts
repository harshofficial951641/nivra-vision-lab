import type { CameraPose } from '../classroom/skeletonGeometry'
import type { CameraLocation } from '../classroom/contracts'
import type { WallCamera } from './model'
import { detectionStatus, type DetectionObservation } from '../classroom/detectionStatus'
export type WallTrack = NonNullable<NonNullable<CameraLocation['result']>['tracks']>[number]

export function wallDetection(camera: WallCamera, now: number) {
  const observation = (result: CameraLocation['result']): DetectionObservation | null => result ? {
    timestampMs: result.timestampMs,
    inferenceMs: result.inferenceMs,
    observedPeople: result.coverage?.observedPeople ?? result.tracks?.length ?? 0,
    usablePeople: result.coverage?.analyzedPeople ?? 0,
    conflict: { status: result.conflict?.status === 'alert' ? 'alert' : result.conflict?.status === 'clear' ? 'clear'
      : result.conflict?.status === 'warming' ? 'warming' : result.conflict?.status === 'observing' ? 'observing' : 'limited', explanation: result.conflict?.explanation ?? '' },
  } : null
  const frame = camera.preview
  // Translate the monitor clock into the phone's monotonic source clock using
  // a received preview. Never compare Date.now() directly to phone performance.now().
  const sourceNow = frame?.timestampMs != null && frame.received != null ? frame.timestampMs + Math.max(0, now - frame.received) : NaN
  return detectionStatus({ phase: camera.sample || camera.status === 'paused' || camera.status === 'offline' ? 'stopped' : camera.status === 'connecting' ? 'reconnecting' : 'live',
    now: sourceNow, crowd: observation(camera.result), motion: observation(camera.motionResult), crowdStatus: camera.deviceStatus, motionStatus: camera.motionStatus })
}

/** The fast motion lane has its own source clock and never moves crowd skeletons. */
export function wallMotion(camera: WallCamera) {
  const motion = camera.motionResult
  if (camera.sample || camera.status !== 'live') return null
  if (!motion) return camera.motionStatus ? { label: camera.motionStatus.state === 'error' ? 'Fast motion unavailable' : 'Fast motion waiting', detail: camera.motionStatus.detail, limited: true } : null
  const status = motion.conflict?.status
  const state = status === 'alert' ? 'Possible conflict · review' : status === 'limited' ? 'Fast motion limited'
    : status === 'warming' ? 'Fast motion warming' : status === 'observing' ? 'Motion observed' : 'Fast motion check'
  const count = motion.coverage?.analyzedPeople ?? 0
  return { label: `${state} · ${count} ${count === 1 ? 'person' : 'people'} · ${Math.round(motion.inferenceMs)} ms`,
    detail: motion.conflict?.explanation ?? '', limited: status === 'limited' }
}

export function observedTracks(tracks: WallTrack[] | undefined): WallTrack[] {
  return (tracks ?? []).filter(track => track.observed === true && Number.isFinite(track.id) &&
    track.box.length === 4 && track.box.every(value => Number.isFinite(value) && value >= 0 && value <= 1) &&
    track.box[2] > track.box[0] && track.box[3] > track.box[1])
}

/** Match device source timestamps, not the phone's clock against the operator's wall clock. */
export function wallTracking(camera: WallCamera, now: number) {
  const frame = camera.preview
  const detail = camera.error || camera.result?.conflict?.explanation || camera.deviceStatus?.detail || ''
  const none = (label: string) => ({ tracks: [] as WallTrack[], poses: [] as CameraPose[], label, detail })
  if (camera.sample) return none('Sample · AI off')
  if (camera.status === 'offline' || camera.status === 'paused') return none(camera.status === 'paused' ? 'AI paused' : 'AI off')
  if (camera.compute !== 'pc' && camera.deviceStatus?.state === 'error') return none('AI error')
  if (camera.compute !== 'pc' && camera.deviceStatus?.state === 'loading') return none('AI loading')
  if (camera.analysis === 'unavailable') return none('AI unavailable')
  if (camera.analysis !== 'current' || !camera.result) return none(camera.deviceStatus?.state === 'ready' ? 'AI ready · waiting for results' : 'AI waiting for results')
  const synchronized = camera.status === 'live' && !!camera.image && frame &&
    Number.isFinite(frame.width) && Number.isFinite(frame.height) && frame.width! > 0 && frame.height! > 0 &&
    Number.isFinite(frame.received) && now - frame.received! >= -1000 && now - frame.received! < (frame.analysisFrame ? 6000 : 2500) &&
    Number.isFinite(frame.timestampMs) && Math.abs(frame.timestampMs! - camera.result.timestampMs) <= 180 &&
    (!frame.generation || frame.generation === camera.generation)
  if (!synchronized) return none('AI delayed · boxes hidden')
  const tracks = observedTracks(camera.result.tracks)
  const count = camera.result.coverage?.observedPeople ?? tracks.length
  const analyzed = camera.result.coverage?.analyzedPeople
  const coverage = camera.result.backend === 'camera-device' && analyzed != null && analyzed < count ? ` · motion ${analyzed}/${count}` : ''
  const prefix = frame?.analysisFrame ? `AI frame · ${(Math.max(0, now - frame.received!) / 1000).toFixed(1)}s ago` : 'AI tracking'
  const motion = camera.result.inferenceMs > 1200 ? ' · motion slow' : ''
  return { tracks, poses: camera.result.poses ?? [], label: tracks.length ? `${prefix} · ${tracks.length} ${tracks.length === 1 ? 'person' : 'people'}${coverage}${motion}` : count > 0 ? `AI sees ${count} · no usable tracks` : 'AI ready · no people tracked', detail }
}

/** Object-fit:contain geometry shared by tiles and viewport-filling camera views. */
export function containedTrackBox(box: number[], frameWidth: number, frameHeight: number, width: number, height: number) {
  const scale = Math.min(width / frameWidth, height / frameHeight)
  if (!Number.isFinite(scale) || scale <= 0) return null
  const imageWidth = frameWidth * scale, imageHeight = frameHeight * scale
  return {
    left: (width - imageWidth) / 2 + box[0] * imageWidth,
    top: (height - imageHeight) / 2 + box[1] * imageHeight,
    width: (box[2] - box[0]) * imageWidth,
    height: (box[3] - box[1]) * imageHeight,
  }
}
