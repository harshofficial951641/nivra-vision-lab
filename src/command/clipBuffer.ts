// In-memory review clips built from preview frames this browser already
// receives. Nothing is uploaded or written to disk; clips disappear when the
// page closes or the incident is decided.

export interface ClipFrame {
  blob: Blob
  /** Client receive time, epoch ms. */
  at: number
}
export interface Clip {
  cameraId: string
  frames: ClipFrame[]
  /** When this browser first saw the incident. */
  peakAt: number
  startAt: number
  endAt: number
  complete: boolean
}

export const BEFORE_MS = 10_000
export const AFTER_MS = 8_000
const MIN_GAP_MS = 150 // keep at most ~6–7 frames per second
const MAX_CLIPS = 6

export class ClipBuffer {
  private rolling = new Map<string, ClipFrame[]>()
  private clips = new Map<string, Clip>()

  push(cameraId: string, blob: Blob, at: number) {
    const frames = this.rolling.get(cameraId) ?? []
    const last = frames.at(-1)
    if (!last || at - last.at >= MIN_GAP_MS) {
      frames.push({ blob, at })
      while (frames.length && at - frames[0].at > BEFORE_MS + 1_000) frames.shift()
      this.rolling.set(cameraId, frames)
    }
    for (const clip of this.clips.values()) {
      if (clip.cameraId !== cameraId || clip.complete) continue
      if (at > clip.endAt) {
        clip.complete = true
        continue
      }
      const previous = clip.frames.at(-1)
      if (!previous || at - previous.at >= MIN_GAP_MS) clip.frames.push({ blob, at })
    }
  }

  /** Start a clip for an incident seen at `at`; idempotent per incident. */
  capture(eventId: string, cameraId: string, at: number) {
    if (this.clips.has(eventId)) return
    const before = (this.rolling.get(cameraId) ?? []).filter(
      (frame) => frame.at >= at - BEFORE_MS && frame.at <= at,
    )
    this.clips.set(eventId, {
      cameraId,
      frames: [...before],
      peakAt: at,
      startAt: at - BEFORE_MS,
      endAt: at + AFTER_MS,
      complete: false,
    })
    while (this.clips.size > MAX_CLIPS) this.clips.delete(this.clips.keys().next().value!)
  }

  /** Mark clips whose after-window has passed even if the camera went quiet. */
  tick(now: number) {
    for (const clip of this.clips.values()) if (!clip.complete && now > clip.endAt) clip.complete = true
  }

  get(eventId: string) {
    const clip = this.clips.get(eventId)
    return clip ? { ...clip, frames: [...clip.frames] } : null
  }

  release(eventId: string) {
    this.clips.delete(eventId)
  }

  clear() {
    this.rolling.clear()
    this.clips.clear()
  }
}
