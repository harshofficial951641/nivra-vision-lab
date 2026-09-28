import { inferenceSize } from '../lib/inferenceSize'
import type { VisionDelegate, VisionWorkerResponse } from '../types/vision'
import { DeviceAnalysis, DEVICE_PEOPLE_LIMIT, type DeviceResult, type DeviceStatus } from './deviceAnalysis'

/** One pose worker and one outstanding bitmap; models live on this camera device. */
export class DeviceVision {
  private worker: Worker | null = null
  private analysis = new DeviceAnalysis()
  private disposed = false
  private ready = false
  private busy = false
  private generation = 0
  private lastCapture = -Infinity
  private pending: { timestamp: number; aspect: number } | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private delegate: VisionDelegate = 'GPU'

  private onStatus: (status: DeviceStatus) => void
  private onResult: (result: DeviceResult) => void

  constructor(onStatus: (status: DeviceStatus) => void, onResult: (result: DeviceResult) => void) {
    this.onStatus = onStatus
    this.onResult = onResult
  }

  start(preferred: VisionDelegate = 'GPU') {
    if (this.disposed) return
    this.generation++
    const epoch = this.generation
    this.worker?.terminate()
    if (this.timer) clearTimeout(this.timer)
    this.ready = false
    this.busy = false
    this.pending = null
    this.analysis = new DeviceAnalysis()
    this.onStatus({ state: 'loading', delegate: null, detail: preferred === 'GPU' ? 'Loading the original Nivra detector on this device…' : 'GPU unavailable. Starting device CPU fallback…' })
    const fail = () => {
      if (this.disposed || this.generation !== epoch) return
      if (preferred === 'GPU') this.start('CPU')
      else {
        this.dispose()
        this.onStatus({ state: 'error', delegate: null, detail: 'Device analysis failed. Video can still stream; reconnect to retry detection.' })
      }
    }
    try {
      const worker = new Worker(new URL('../workers/vision.worker.ts', import.meta.url), { type: 'module' })
      this.worker = worker
      this.timer = setTimeout(fail, 30000)
      worker.onerror = fail
      worker.onmessageerror = fail
      worker.onmessage = ({ data }: MessageEvent<VisionWorkerResponse>) => {
        if (this.disposed || this.worker !== worker) return
        if (data.type === 'error') { fail(); return }
        if (data.type === 'ready') {
          if (this.timer) clearTimeout(this.timer)
          this.delegate = data.delegate
          this.ready = true
          this.onStatus({ state: 'ready', delegate: data.delegate, detail: data.delegate === 'GPU' ? 'Device GPU · original Nivra motion detector' : 'Device CPU fallback · GPU acceleration unavailable' })
        }
        if (data.type === 'pose-result' && data.timestampMs === this.pending?.timestamp) {
          if (this.timer) clearTimeout(this.timer)
          const aspect = this.pending.aspect
          this.pending = null
          this.busy = false
          this.onResult(this.analysis.update(data.timestampMs, data.inferenceMs, data.poses, aspect, this.delegate))
        }
      }
      worker.postMessage({
        type: 'init', task: 'pose', poseDelegate: preferred,
        modelPath: `${import.meta.env.BASE_URL}models/pose_landmarker_lite.task`,
        wasmRoot: import.meta.env.DEV ? `${import.meta.env.BASE_URL}__nivra_wasm` : `${import.meta.env.BASE_URL}mediapipe/wasm`,
        maxPoses: DEVICE_PEOPLE_LIMIT, poseConfidence: 0.5, objectConfidence: 0.35,
      })
    } catch { fail() }
  }

  async capture(video: HTMLVideoElement, timestamp: number) {
    if (this.disposed || !this.ready || this.busy || timestamp - this.lastCapture < 100 || video.readyState < 2 || !video.videoWidth) return
    this.busy = true
    this.lastCapture = timestamp
    const generation = this.generation
    let bitmap: ImageBitmap | null = null
    try {
      const size = inferenceSize({ width: video.videoWidth, height: video.videoHeight }, 640)
      bitmap = await createImageBitmap(video, { resizeWidth: size.width, resizeHeight: size.height, resizeQuality: 'medium' })
      if (this.disposed || generation !== this.generation) { bitmap.close(); return }
      this.pending = { timestamp, aspect: video.videoWidth / video.videoHeight }
      this.timer = setTimeout(() => {
        if (this.delegate === 'GPU') this.start('CPU')
        else {
          this.dispose()
          this.onStatus({ state: 'error', delegate: null, detail: 'Device too slow or analysis stalled. Video only; reconnect to retry detection.' })
        }
      }, this.delegate === 'GPU' ? 5000 : 10000)
      this.worker!.postMessage({ type: 'frame', bitmap, timestampMs: timestamp }, [bitmap])
    } catch {
      bitmap?.close()
      if (this.disposed || generation !== this.generation) return
      this.dispose()
      this.onStatus({ state: 'error', delegate: null, detail: 'This browser cannot process camera frames. Video only; try a current browser.' })
    }
  }

  dispose() {
    this.disposed = true
    this.generation++
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate()
    this.worker = null
    this.pending = null
  }
}
