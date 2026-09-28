import { ConflictEngine } from '../lib/conflictEngine'
import type { PoseLandmarks, VisionDelegate } from '../types/vision'
import { analysisRegion, type AnalysisArea } from './deviceBudget'

export const DEVICE_MODEL = 'nivra-browser-motion-v1'
export const DEVICE_PEOPLE_LIMIT = 10

/** Reuses the original Nivra single-hit detector with smaller-body admission; impact thresholds stay unchanged. */
export class DeviceAnalysis {
  private engine = new ConflictEngine({ minBodyScale: .035, minShoulderWidth: .0275 })
  private runId = crypto.randomUUID()

  update(timestampMs: number, inferenceMs: number, poses: PoseLandmarks[], aspect: number, delegate: VisionDelegate, area: AnalysisArea = 'full') {
    const conflict = this.engine.update(timestampMs, poses, aspect)
    const region = analysisRegion(area)
    return {
      type: 'device-result' as const,
      model: DEVICE_MODEL,
      delegate,
      timestampMs,
      inferenceMs,
      observedPeople: poses.length,
      usablePeople: conflict.people,
      // Original browser tracking has no robust occlusion identity assurance.
      tracks: this.engine.observedTracks().map(({ id, box }) => ({
        id, box: [region.x + box.x * region.width, region.y + box.y * region.height,
          region.x + (box.x + box.width) * region.width, region.y + (box.y + box.height) * region.height],
      })),
      conflict: { status: conflict.status, explanation: conflict.explanation },
      events: conflict.events.filter(event => timestampMs - event.occurredAtMs <= 5000).slice(-2).map(event => ({
        id: `${this.runId}-${event.id}`, occurredAtMs: event.occurredAtMs, detail: event.detail,
      })),
    }
  }
}

export type DeviceResult = ReturnType<DeviceAnalysis['update']>
export type DeviceStatus = {
  state: 'loading' | 'ready' | 'error'
  delegate: VisionDelegate | null
  detail: string
}
