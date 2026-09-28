import type { VisionResult } from './VisionWorkerClient'
import type { ConflictSnapshot } from '../lib/conflictEngine'

export interface LocalPersonTrack {
  id: number
  box: [number, number, number, number]
  observed: boolean
  ambiguous: boolean
  partial: boolean
  keypoints: Array<[number, number, number]>
}

export interface LocalActionEvidence {
  trackId: number
  hit: number
  push: number
  grab: number
}

export interface LocalRuntime {
  action: string
  detector: string
  pose: string
  personModel?: 'yolox' | 'rtmo'
  fightModel?: 'ava' | 'x3d'
  maxPeople?: number
}

export interface LocalVisionResult extends VisionResult {
  version: 1
  backend: 'local-ai'
  streamId: number
  evidenceTimestampMs: number
  conflict: ConflictSnapshot
  tracks: LocalPersonTrack[]
  actions: LocalActionEvidence[]
  runtime: LocalRuntime
  fightEvidence?: { backboneScore: number; publisherScore: number; startMs: number; endMs: number; model: string } | null
  coverage?: { observedPeople: number; analyzedPeople: number; excludedPeople: number; status: 'limited' | 'analyzing'; personLimit: number; actionView: string; actionPeople: number; actionEvidenceTimestampMs: number }
  experimental: true
}

export class LocalVisionClient {
  private socket: WebSocket | null = null
  private generation = 0
  private pending: { generation: number; timestamp: number } | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  private maxPeople = 4
  private callbacks: { ready(runtime?: LocalRuntime): void; result(result: LocalVisionResult): void; error(message: string): void }
  constructor(callbacks: { ready(runtime?: LocalRuntime): void; result(result: LocalVisionResult): void; error(message: string): void }) { this.callbacks = callbacks }

  async connect() {
    try {
      const response = await fetch('/api/v1/session', { method: 'POST', credentials: 'same-origin' })
      if (!response.ok) throw new Error('Open the app using the local AI launcher at http://127.0.0.1:8765.')
      let ready = false
      let runtime: LocalRuntime | undefined
      for (let attempt = 0; attempt < 120 && !this.disposed; attempt++) {
        const health = await fetch('/api/v1/health', { cache: 'no-store' }).then(r => r.json())
        if (health.status === 'error') throw new Error(health.error || 'Local model initialization failed.')
        if (health.status === 'ready') { ready = true; runtime = health.runtime; break }
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
      if (this.disposed) return
      if (!ready) throw new Error('Local model loading timed out. Restart the service.')
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/stream`)
      this.socket = socket
      socket.onopen = () => { if (!this.disposed) this.callbacks.ready(runtime) }
      socket.onmessage = event => {
        if (this.disposed) return
        try {
          const result = JSON.parse(event.data) as LocalVisionResult
          const pending = this.pending
          if (!pending || result.streamId !== pending.generation || result.timestampMs !== pending.timestamp) return
          this.clearPending()
          if (result.streamId !== this.generation) return
          if (result.version !== 1 || result.backend !== 'local-ai' || !result.conflict || !Array.isArray(result.poses)) throw new Error('Invalid local analysis response.')
          this.callbacks.result(result)
        } catch { this.fail('The local service returned an invalid response. Restart analysis.') }
      }
      socket.onclose = () => { if (!this.disposed) this.fail('Local AI disconnected. Restart analysis or explicitly choose Browser mode.') }
      socket.onerror = () => this.fail('Local AI is unavailable. Check the local service and retry.')
    } catch (error) {
      if (!this.disposed) this.fail(error instanceof Error ? error.message : 'Local AI connection failed.')
    }
  }

  get isBusy() { return this.pending !== null || this.socket?.readyState !== WebSocket.OPEN }
  configure(maxPeople: number) { this.maxPeople = maxPeople }
  resetStream() {
    this.generation++
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'reset', streamId: this.generation }))
  }

  submitFrame(bitmap: ImageBitmap, objectBitmap: ImageBitmap | null, timestampMs: number) {
    objectBitmap?.close()
    if (this.isBusy || this.disposed) { bitmap.close(); return false }
    const generation = this.generation
    this.pending = { generation, timestamp: timestampMs }
    this.timer = setTimeout(() => this.fail('Local inference timed out. Restart analysis.'), 15000)
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height)
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0)
    bitmap.close()
    void canvas.convertToBlob({ type: 'image/jpeg', quality: .85 }).then(async blob => {
      const header = new TextEncoder().encode(JSON.stringify({ version: 1, timestampMs, streamId: generation, maxPeople: this.maxPeople }))
      const jpeg = await blob.arrayBuffer()
      if (this.disposed || generation !== this.generation) { this.clearPending(); return }
      const packet = new Uint8Array(4 + header.length + jpeg.byteLength)
      new DataView(packet.buffer).setUint32(0, header.length, true)
      packet.set(header, 4)
      packet.set(new Uint8Array(jpeg), 4 + header.length)
      this.socket?.send(packet)
    }).catch(() => this.fail('A camera frame could not be sent to local AI.'))
    return true
  }

  private clearPending() {
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    this.pending = null
  }
  private fail(message: string) {
    if (this.disposed) return
    this.dispose()
    this.callbacks.error(message)
  }
  dispose() {
    this.disposed = true
    this.clearPending()
    this.socket?.close()
    this.socket = null
  }
}
