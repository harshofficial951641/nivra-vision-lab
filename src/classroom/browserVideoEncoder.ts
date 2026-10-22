/** Browser H264 is optional. Unsupported encoders keep the JPEG transport. */
export interface BrowserVideoBatch {
  type: 'browser-video-v1'; version: 1; generation: string; codec: string; description: string
  width: number; height: number
  frames: { sequence: number; timestampMs: number; keyframe: boolean; data: string }[]
}
export interface BrowserVideoOptions {
  onBatch: (batch: BrowserVideoBatch) => void
  onFailure: () => void
  canSend: () => boolean
}
const base64 = (bytes: Uint8Array) => {
  let text = ''
  for (let i = 0; i < bytes.length; i += 16384) text += String.fromCharCode(...bytes.subarray(i, i + 16384))
  return btoa(text)
}
export class BrowserVideoEncoder {
  private encoder: VideoEncoder | null = null
  private video: HTMLVideoElement | null = null
  private options: BrowserVideoOptions
  private callback = 0
  private timer: ReturnType<typeof setInterval> | undefined
  private disposed = false
  private supportChecks = new Map<ReturnType<typeof setTimeout>, () => void>()
  private generation = crypto.randomUUID()
  private description = ''
  private codec = ''
  private sourceWidth = 0
  private sourceHeight = 0
  private width = 0
  private height = 0
  private sequence = 0
  private pending: BrowserVideoBatch['frames'] = []
  private pendingBytes = 0
  private waitingKey = true
  private forceKey = true
  private lastKey = -Infinity
  private lastCapture = -Infinity
  private nextCapture = -Infinity
  private transportAfter = -Infinity
  private lastOutput = -Infinity
  private firstInputAt = -Infinity
  private lastOutputAt = -Infinity
  private submitted = 0
  private encoded = 0
  private sent = 0
  private dropped = 0
  constructor(options: BrowserVideoOptions) { this.options = options }
  private supported(config: VideoEncoderConfig): Promise<boolean> {
    return new Promise(resolve => {
      let settled = false
      const finish = (value: boolean) => { if (settled) return; settled = true; clearTimeout(timer); this.supportChecks.delete(timer); resolve(value) }
      const timer = setTimeout(() => finish(false), 1000)
      this.supportChecks.set(timer, () => finish(false))
      VideoEncoder.isConfigSupported(config).then(result => finish(!!result.supported), () => finish(false))
    })
  }
  async start(video: HTMLVideoElement): Promise<boolean> {
    if (this.disposed || this.encoder || typeof VideoEncoder === 'undefined' || typeof VideoFrame === 'undefined' || !video.requestVideoFrameCallback || !video.videoWidth || !video.videoHeight) return false
    this.sourceWidth = video.videoWidth; this.sourceHeight = video.videoHeight
    const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight))
    this.width = Math.max(32, Math.floor(video.videoWidth * scale / 2) * 2)
    this.height = Math.max(32, Math.floor(video.videoHeight * scale / 2) * 2)
    let config: VideoEncoderConfig = { codec: 'avc1.42002a', width: this.width, height: this.height, bitrate: 4_000_000, framerate: 40, latencyMode: 'realtime', hardwareAcceleration: 'prefer-hardware', avc: { format: 'avc' } }
    try {
      let supported = await this.supported(config)
      if (!supported && !this.disposed) {
        config = { ...config, hardwareAcceleration: 'no-preference' }
        supported = await this.supported(config)
      }
      if (!supported || this.disposed) return false
      this.video = video
      this.encoder = new VideoEncoder({ output: (chunk, metadata) => this.output(chunk, metadata), error: () => this.fail() })
      this.encoder.configure(config)
      this.firstInputAt = performance.now()
      this.timer = setInterval(() => {
        this.flush()
        // A configured encoder that never outputs cannot silently suppress JPEG.
        if (performance.now() - Math.max(this.firstInputAt, this.lastOutputAt) > 3000) this.fail()
      }, 100)
      this.schedule()
      return true
    } catch { this.dispose(); return false }
  }
  private schedule() {
    if (!this.disposed && this.video) this.callback = this.video.requestVideoFrameCallback(now => { this.capture(now); this.schedule() })
  }
  private capture(now: number) {
    const encoder = this.encoder, video = this.video
    if (!encoder || !video || encoder.state !== 'configured' || video.readyState < 2) return
    if (video.videoWidth !== this.sourceWidth || video.videoHeight !== this.sourceHeight) { this.fail(); return }
    if (now + .5 < this.nextCapture) return
    if (!this.options.canSend() || encoder.encodeQueueSize >= 2) { this.dropped++; this.forceKey = true; return }
    const keyFrame = this.forceKey || now - this.lastKey >= 1000
    let frame: VideoFrame | undefined
    try {
      frame = new VideoFrame(video, { timestamp: Math.round(now * 1000) })
      encoder.encode(frame, { keyFrame })
      if (!this.submitted) this.firstInputAt = performance.now()
      this.submitted++; this.lastCapture = now
      this.nextCapture = Number.isFinite(this.nextCapture) ? Math.max(this.nextCapture + 25, now) : now + 25
      if (keyFrame) { this.forceKey = false; this.lastKey = now }
    } catch { this.fail() } finally { frame?.close() }
  }
  private output(chunk: EncodedVideoChunk, metadata?: EncodedVideoChunkMetadata) {
    if (this.disposed) return
    const config = metadata?.decoderConfig
    if (config?.description) {
      const raw = config.description
      const bytes = ArrayBuffer.isView(raw) ? new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength) : new Uint8Array(raw)
      if (bytes.length < 7 || bytes.length > 4096 || bytes[0] !== 1 || (bytes[4] & 3) !== 3) { this.fail(); return }
      this.description = base64(bytes)
      this.codec = 'avc1.' + [...bytes.subarray(1, 4)].map(n => n.toString(16).padStart(2, '0')).join('')
    }
    const stamp = chunk.timestamp / 1000, keyframe = chunk.type === 'key'
    this.encoded++; this.lastOutputAt = performance.now()
    if (!Number.isFinite(stamp) || stamp <= this.lastOutput || chunk.byteLength > 1_000_000) { this.fail(); return }
    this.lastOutput = stamp
    if (stamp < this.transportAfter) { this.dropped++; return }
    if (!this.description || !this.options.canSend()) { this.pending = []; this.pendingBytes = 0; this.waitingKey = true; this.forceKey = true; this.dropped++; return }
    if (this.waitingKey && !keyframe) { this.dropped++; return }
    if (keyframe) this.waitingKey = false
    if (this.pending.length >= 8 || this.pendingBytes + chunk.byteLength > 1_000_000) {
      this.pending = []; this.pendingBytes = 0; this.waitingKey = true; this.forceKey = true; this.dropped++
      if (!keyframe) return
      this.waitingKey = false
    }
    const bytes = new Uint8Array(chunk.byteLength); chunk.copyTo(bytes)
    this.pending.push({ sequence: ++this.sequence, timestampMs: stamp, keyframe, data: base64(bytes) }); this.pendingBytes += bytes.length
  }
  private flush() {
    if (this.disposed || !this.pending.length) return
    if (!this.options.canSend()) { this.resetTransport(); return }
    const frames = this.pending; this.pending = []; this.pendingBytes = 0
    try { this.options.onBatch({ type: 'browser-video-v1', version: 1, generation: this.generation, codec: this.codec, description: this.description, width: this.width, height: this.height, frames }); this.sent += frames.length } catch { this.fail() }
  }
  /** A new socket must begin a new generation at a fresh IDR. Encoder stays warm. */
  resetTransport() { this.transportAfter = Math.max(performance.now(), this.lastCapture + .001); this.pending = []; this.pendingBytes = 0; this.generation = crypto.randomUUID(); this.waitingKey = true; this.forceKey = true }
  metrics() { return { submitted: this.submitted, encoded: this.encoded, sent: this.sent, dropped: this.dropped, queue: this.encoder?.encodeQueueSize ?? 0 } }
  private fail() { if (this.disposed) return; this.dispose(); this.options.onFailure() }
  dispose() {
    if (this.disposed) return
    this.disposed = true
    for (const cancel of this.supportChecks.values()) cancel()
    this.supportChecks.clear()
    if (this.callback) this.video?.cancelVideoFrameCallback(this.callback)
    clearInterval(this.timer)
    try { this.encoder?.close() } catch { /* Already failed. */ }
    this.encoder = null; this.video = null; this.pending = []; this.pendingBytes = 0
  }
}
