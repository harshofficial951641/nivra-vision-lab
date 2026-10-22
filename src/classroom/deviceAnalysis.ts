import { ConflictEngine } from '../lib/conflictEngine'
import type { PoseLandmarks, VisionDelegate } from '../types/vision'
import { analysisRegion, type AnalysisArea } from './deviceBudget'
import { mergePersonBoxes, PersonTracker, type PersonBox, type PersonObservation } from './personTracking'
import { DEVICE_POSE_LIMIT } from './capacity'
import type { ReviewEvent } from '../lib/sceneEngine'

export const DEVICE_MODEL = 'nivra-browser-motion-v1'
export { DEVICE_PEOPLE_LIMIT, DEVICE_POSE_LIMIT } from './capacity'
export type ObservedJoint = [number, number, number] | null

/** Camera-device arm-motion rules; review signals are not a trained fight classification. */
export class DeviceAnalysis {
  private engine: Pick<ConflictEngine, 'update' | 'observedTracks'>
  constructor(engine: Pick<ConflictEngine, 'update' | 'observedTracks'> = new ConflictEngine({ minBodyScale: .035, minShoulderWidth: .0275, maxGapMs: 3000 })) {
    this.engine = engine
  }
  private runId = crypto.randomUUID()
  private people = new PersonTracker()
  private lastTimestamp = -Infinity
  private pendingEvents = new Map<string, ReviewEvent>()
  private emittedEvents = new Map<string, number>()

  update(timestampMs: number, inferenceMs: number, poses: PoseLandmarks[], aspect: number, delegate: VisionDelegate, area: AnalysisArea = 'full', personObservations?: readonly PersonObservation[]) {
    const conflict = this.engine.update(timestampMs, poses, aspect)
    const interval = timestampMs - this.lastTimestamp
    const sparse = Number.isFinite(interval) && interval > 1200
    if (Number.isFinite(timestampMs) && timestampMs > this.lastTimestamp) this.lastTimestamp = timestampMs
    const region = analysisRegion(area)
    const poseTracks = this.engine.observedTracks().map(({ id, box }) => ({
      id, box: [region.x + box.x * region.width, region.y + box.y * region.height,
        region.x + (box.x + box.width) * region.width, region.y + (box.y + box.height) * region.height] as PersonBox,
    }))
    const tracks = personObservations === undefined ? poseTracks :
      // These poses were proposed by the same person detections. A distorted
      // pose must never become an extra counted person outside those detections.
      this.people.update(timestampMs, mergePersonBoxes(personObservations, []))
    const skeletons = poses.slice(0, DEVICE_POSE_LIMIT).map(pose => Array.from({ length: 33 }, (_, i): ObservedJoint => {
      const point = pose[i]
      if (!point) return null
      const visibility = point.visibility
      if (![point.x, point.y, visibility].every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1)) return null
      return [region.x + point.x * region.width, region.y + point.y * region.height, visibility!]
        .map(v => Math.round(v * 10000) / 10000) as [number, number, number]
    })).filter(pose => pose.some(point => point !== null))
    for (const [id, event] of this.pendingEvents) if (timestampMs - event.occurredAtMs > 5000) this.pendingEvents.delete(id)
    for (const [id, time] of this.emittedEvents) if (timestampMs - time > 5000) this.emittedEvents.delete(id)
    for (const event of conflict.events) {
      if (timestampMs - event.occurredAtMs <= 5000 && !this.emittedEvents.has(event.id) && !this.pendingEvents.has(event.id) && this.pendingEvents.size < 32)
        this.pendingEvents.set(event.id, event)
    }
    const events = [...this.pendingEvents.values()].slice(0, 2)
    for (const event of events) {
      this.pendingEvents.delete(event.id)
      this.emittedEvents.set(event.id, event.occurredAtMs)
    }
    while (this.emittedEvents.size > 64) this.emittedEvents.delete(this.emittedEvents.keys().next().value!)
    return {
      type: 'device-result' as const,
      model: DEVICE_MODEL,
      delegate,
      timestampMs,
      inferenceMs,
      observedPeople: personObservations === undefined ? poses.length : tracks.length,
      usablePeople: conflict.people,
      // Original browser tracking has no robust occlusion identity assurance.
      tracks,
      poses: skeletons,
      conflict: (inferenceMs > 1200 || sparse) && conflict.status !== 'alert'
        ? { status: 'limited' as const, explanation: `${sparse ? `Pose updates are ${(interval / 1000).toFixed(1)} seconds apart.` : `Pose analysis took ${(inferenceMs / 1000).toFixed(1)} seconds.`} Motion sampling is too slow for reliable conflict review. Use a faster camera device or fewer students per camera view.` }
        : { status: conflict.status, explanation: conflict.explanation },
      events: events.map(event => ({
        id: `${this.runId}-${event.id}`, occurredAtMs: event.occurredAtMs, detail: event.detail,
      })),
    }
  }
}

export type DeviceResult = ReturnType<DeviceAnalysis['update']>
export type DeviceMotion = Omit<DeviceResult, 'type'> & { type: 'device-motion' }
export type DeviceStatus = {
  state: 'loading' | 'ready' | 'error'
  delegate: VisionDelegate | null
  detail: string
}
