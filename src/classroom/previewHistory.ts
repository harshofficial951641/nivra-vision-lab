export interface CameraPreview {
  url: string
  generation: string
  received: number
  timestampMs: number
  width: number
  height: number
  analysisFrame?: boolean
}
export type PreviewMetadata = Omit<CameraPreview, 'url' | 'received' | 'analysisFrame'>

/** Sampled JPEGs for drawing analysis on its own source frame, with bounded URL ownership. */
export class PreviewHistory {
  private frames = new Map<string, CameraPreview[]>()
  private create: (image: Blob) => string
  private revoke: (url: string) => void
  constructor(create = (image: Blob) => URL.createObjectURL(image), revoke = (url: string) => URL.revokeObjectURL(url)) { this.create = create; this.revoke = revoke }
  private release(frames: CameraPreview[]) { frames.forEach(frame => this.revoke(frame.url)) }
  private prune(id: string, now: number, sourceTime?: number) {
    const old = this.frames.get(id) ?? []
    const keep = old.filter(frame => now - frame.received <= 6000 && now - frame.received >= -1000 && (sourceTime === undefined || sourceTime - frame.timestampMs <= 6000))
    old.filter(frame => !keep.includes(frame)).forEach(frame => this.revoke(frame.url))
    this.frames.set(id, keep)
    return keep
  }
  add(id: string, meta: PreviewMetadata, image: Blob, received: number) {
    if (!meta.generation || ![meta.timestampMs, received, meta.width, meta.height].every(Number.isFinite) || meta.timestampMs < 0 || meta.width <= 0 || meta.height <= 0) return
    let frames = this.frames.get(id) ?? []
    if (frames.some(frame => frame.generation !== meta.generation)) { this.release(frames); frames = []; this.frames.set(id, frames) }
    frames = this.prune(id, received, meta.timestampMs)
    const last = frames.at(-1)
    // A ~200 ms source cadence spans six seconds without retaining every live JPEG.
    if (last && meta.timestampMs - last.timestampMs < 200) return
    frames.push({ ...meta, url: this.create(image), received })
    while (frames.length > 32) this.revoke(frames.shift()!.url)
    this.frames.set(id, frames)
  }
  select(id: string, generation: string, timestampMs: number, now: number): CameraPreview | undefined {
    if (!Number.isFinite(timestampMs)) return
    let best: CameraPreview | undefined
    for (const frame of this.prune(id, now)) {
      if (frame.generation !== generation || Math.abs(frame.timestampMs - timestampMs) > 180) continue
      if (!best || Math.abs(frame.timestampMs - timestampMs) < Math.abs(best.timestampMs - timestampMs)) best = frame
    }
    return best && { ...best, analysisFrame: true }
  }
  retain(active: ReadonlyMap<string, string | null>) {
    for (const [id, frames] of this.frames) {
      const keep = frames.filter(frame => active.get(id) === frame.generation)
      this.release(frames.filter(frame => !keep.includes(frame)))
      if (keep.length) this.frames.set(id, keep)
      else this.frames.delete(id)
    }
  }
  clear() { this.frames.forEach(frames => this.release(frames)); this.frames.clear() }
}
