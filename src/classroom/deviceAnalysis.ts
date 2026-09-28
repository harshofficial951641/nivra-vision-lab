import { ConflictEngine } from '../lib/conflictEngine'
import type { PoseLandmarks, VisionDelegate } from '../types/vision'

export const DEVICE_MODEL = 'nivra-browser-motion-v1'
export const DEVICE_PEOPLE_LIMIT = 4

/** Reuses the original Nivra single-hit detector without changing its thresholds. */
export class DeviceAnalysis {
  private engine = new ConflictEngine()
  private runId = crypto.randomUUID()

  update(timestampMs: number, inferenceMs: number, poses: PoseLandmarks[], aspect: number, delegate: VisionDelegate) {
    const conflict = this.engine.update(timestampMs, poses, aspect)
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
        id, box: [box.x, box.y, box.x + box.width, box.y + box.height],
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
