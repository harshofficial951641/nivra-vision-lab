import type { PeopleResult, PeopleWorkerResponse } from './peopleContracts'
export type { PeopleResult, PersonObservation } from './peopleContracts'

/** One CPU person detector and at most one transferred image, separate from pose work. */
export class PeopleVision {
  private worker: Worker | null = null
  private disposed = false
  private ready = false
  private initialization: Promise<void> | null = null
  private resolveReady: (() => void) | null = null
  private rejectReady: ((reason: Error) => void) | null = null
  private pending: { timestampMs: number; resolve: (result: PeopleResult) => void; reject: (reason: Error) => void } | null = null
  private timer: ReturnType<typeof setTimeout> | null = null

  start(): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('Person detection stopped.'))
    if (this.initialization) return this.initialization
    this.initialization = new Promise((resolve, reject) => { this.resolveReady = resolve; this.rejectReady = reject })
    try {
      const worker = new Worker(new URL('../workers/people.worker.ts', import.meta.url), { type: 'module' })
      this.worker = worker
      worker.onerror = () => this.fail(new Error('Person detection worker failed. Reconnect the camera to retry.'))
      worker.onmessageerror = () => this.fail(new Error('Person detection returned an unreadable result.'))
      worker.onmessage = ({ data }: MessageEvent<PeopleWorkerResponse>) => {
        if (this.disposed || this.worker !== worker) return
        if (data.type === 'error') { this.fail(new Error(data.message)); return }
        if (data.type === 'ready') {
          if (this.timer) clearTimeout(this.timer)
          this.ready = true
          this.resolveReady?.()
          this.resolveReady = this.rejectReady = null
        }
        if (data.type === 'people-result' && data.result.timestampMs === this.pending?.timestampMs) {
          if (this.timer) clearTimeout(this.timer)
          const pending = this.pending
          this.pending = null
          pending.resolve(data.result)
        }
      }
      this.timer = setTimeout(() => this.fail(new Error('Person model loading timed out. Reconnect to retry.')), 30_000)
      worker.postMessage({ type: 'init', modelPath: `${import.meta.env.BASE_URL}models/efficientdet_lite0_float16.tflite`,
        wasmRoot: import.meta.env.DEV ? `${import.meta.env.BASE_URL}__nivra_wasm` : `${import.meta.env.BASE_URL}mediapipe/wasm` })
    } catch (reason) { this.fail(reason instanceof Error ? reason : new Error('Person detector could not start.')) }
    return this.initialization
  }

  /** Takes ownership of bitmap on success AND rejection. The caller must not reuse it. */
  analyze(bitmap: ImageBitmap, timestampMs: number): Promise<PeopleResult> {
    if (this.disposed || !this.ready || !this.worker || this.pending || !Number.isFinite(timestampMs) || timestampMs < 0) {
      bitmap.close()
      return Promise.reject(new Error(this.pending ? 'Person detector is already processing a frame.' : 'Person detector is not ready.'))
    }
    return new Promise((resolve, reject) => {
      this.pending = { timestampMs, resolve, reject }
      this.timer = setTimeout(() => this.fail(new Error('Person detection stalled. Reconnect the camera to retry.')), 10_000)
      try { this.worker!.postMessage({ type: 'frame', bitmap, timestampMs }, [bitmap]) }
      catch (reason) {
        bitmap.close()
        this.fail(reason instanceof Error ? reason : new Error('The camera image could not be sent to person detection.'))
      }
    })
  }

  private fail(reason: Error) {
    this.disposed = true
    this.ready = false
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate()
    this.worker = null
    this.rejectReady?.(reason)
    this.pending?.reject(reason)
    this.pending = null
    this.resolveReady = this.rejectReady = null
  }
  dispose() { this.fail(new Error('Person detection stopped.')) }
}
