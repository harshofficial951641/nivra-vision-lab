import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BrowserVideoEncoder } from './browserVideoEncoder'
class FakeEncoder {
  static supported = true
  static last: FakeEncoder
  static isConfigSupported = vi.fn(async (_config: VideoEncoderConfig) => ({ supported: FakeEncoder.supported }))
  state = 'configured'
  encodeQueueSize = 0
  configure = vi.fn()
  encode = vi.fn()
  close = vi.fn(() => { this.state = 'closed' })
  output: VideoEncoderInit['output']
  constructor(init: VideoEncoderInit) { FakeEncoder.last = this; this.output = init.output }
  emit(time: number, key = true) {
    const bytes = new Uint8Array([0, 0, 0, 2, 0x65, 0x88])
    this.output({ timestamp: time * 1000, type: key ? 'key' : 'delta', byteLength: bytes.length, copyTo: (target: Uint8Array) => target.set(bytes) } as unknown as EncodedVideoChunk,
      { decoderConfig: { codec: 'avc1.42002a', description: new Uint8Array([1, 0x42, 0, 0x2a, 0xff, 0xe1, 0]) } })
  }
}
let callback: VideoFrameRequestCallback
const cancel = vi.fn()
const video = { videoWidth: 1280, videoHeight: 720, readyState: 4, requestVideoFrameCallback: vi.fn((cb: VideoFrameRequestCallback) => { callback = cb; return 1 }), cancelVideoFrameCallback: cancel } as unknown as HTMLVideoElement
const tick = (now: number) => callback(now, {} as VideoFrameCallbackMetadata)
beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal('VideoEncoder', FakeEncoder)
  vi.stubGlobal('VideoFrame', class { close = vi.fn() })
  FakeEncoder.supported = true; vi.clearAllMocks(); FakeEncoder.isConfigSupported.mockImplementation(async () => ({ supported: FakeEncoder.supported }))
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
it('falls back without touching camera when H264 configuration is unsupported', async () => {
  FakeEncoder.supported = false
  const client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure: vi.fn(), canSend: () => true })
  expect(await client.start(video)).toBe(false)
  expect(video.requestVideoFrameCallback).not.toHaveBeenCalled()
})
it('emits AVCC configuration with actual source timestamps and distinct browser protocol', async () => {
  const onBatch = vi.fn(), client = new BrowserVideoEncoder({ onBatch, onFailure: vi.fn(), canSend: () => true })
  expect(await client.start(video)).toBe(true)
  tick(100); FakeEncoder.last.emit(100)
  await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'browser-video-v1', codec: 'avc1.42002a', width: 1280, height: 720, frames: [expect.objectContaining({ timestampMs: 100, keyframe: true })] }))
  client.dispose(); expect(cancel).toHaveBeenCalled()
})
it('bounds encoder backlog and resumes a new transport only at a fresh keyframe', async () => {
  let available = true
  const onBatch = vi.fn(), client = new BrowserVideoEncoder({ onBatch, onFailure: vi.fn(), canSend: () => available })
  await client.start(video); tick(100); FakeEncoder.last.emit(100); await vi.advanceTimersByTimeAsync(100)
  const firstGeneration = onBatch.mock.calls[0][0].generation
  FakeEncoder.last.encodeQueueSize = 2; tick(125); expect(FakeEncoder.last.encode).toHaveBeenCalledTimes(1)
  FakeEncoder.last.encodeQueueSize = 0; available = false; tick(150); expect(FakeEncoder.last.encode).toHaveBeenCalledTimes(1)
  available = true; client.resetTransport(); tick(175)
  expect(FakeEncoder.last.encode).toHaveBeenLastCalledWith(expect.anything(), { keyFrame: true })
  FakeEncoder.last.emit(175, false); await vi.advanceTimersByTimeAsync(100); expect(onBatch).toHaveBeenCalledTimes(1)
  tick(200); FakeEncoder.last.emit(200); await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).toHaveBeenCalledTimes(2); expect(onBatch.mock.calls[1][0].generation).not.toBe(firstGeneration)
  client.dispose()
})
it('reports a stalled real encoder and releases callbacks without an unbounded flush', async () => {
  const onFailure = vi.fn(), client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure, canSend: () => true })
  await client.start(video); tick(100)
  await vi.advanceTimersByTimeAsync(3200)
  expect(onFailure).toHaveBeenCalledOnce(); expect(FakeEncoder.last.close).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(5000); expect(onFailure).toHaveBeenCalledOnce()
})
it('caps sixty source frames per second near forty without synthesizing frames', async () => {
  const client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure: vi.fn(), canSend: () => true })
  await client.start(video)
  for (let i = 0; i < 60; i++) tick(i * 1000 / 60)
  expect(FakeEncoder.last.encode.mock.calls.length).toBeGreaterThanOrEqual(39)
  expect(FakeEncoder.last.encode.mock.calls.length).toBeLessThanOrEqual(40)
  client.dispose()
})

it('falls back on source orientation changes instead of stretching portrait video', async () => {
  const onFailure = vi.fn(), source = { ...video } as HTMLVideoElement
  const client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure, canSend: () => true })
  await client.start(source)
  Object.defineProperties(source, { videoWidth: { value: 720 }, videoHeight: { value: 1280 } })
  tick(100)
  expect(onFailure).toHaveBeenCalledOnce()
  expect(FakeEncoder.last.encode).not.toHaveBeenCalled()
})

it('tries no-preference when the hardware hint is unsupported without claiming hardware', async () => {
  FakeEncoder.isConfigSupported.mockImplementation(async (config: VideoEncoderConfig) => ({ supported: config.hardwareAcceleration === 'no-preference' }))
  const client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure: vi.fn(), canSend: () => true })
  expect(await client.start(video)).toBe(true)
  expect(FakeEncoder.isConfigSupported).toHaveBeenCalledTimes(2)
  expect(FakeEncoder.last.configure).toHaveBeenCalledWith(expect.objectContaining({ hardwareAcceleration: 'no-preference' }))
  client.dispose()
})

it('bounds a stalled capability check and cancels pending initialization on Stop', async () => {
  FakeEncoder.isConfigSupported.mockReturnValue(new Promise(() => {}))
  const client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure: vi.fn(), canSend: () => true })
  const started = client.start(video)
  await vi.advanceTimersByTimeAsync(1000)
  expect(FakeEncoder.isConfigSupported).toHaveBeenCalledTimes(2)
  client.dispose()
  expect(await started).toBe(false)
  expect(vi.getTimerCount()).toBe(0)
})
it('allows slow first camera frames but still bounds a permanently missing source', async () => {
  const onFailure = vi.fn(), client = new BrowserVideoEncoder({ onBatch: vi.fn(), onFailure, canSend: () => true })
  await client.start(video)
  await vi.advanceTimersByTimeAsync(10000)
  expect(onFailure).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(5200)
  expect(onFailure).toHaveBeenCalledOnce()
  expect(FakeEncoder.last.encode).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})
it('never labels queued pre-reconnect keyframes as fresh transport video', async () => {
  const onBatch = vi.fn(), client = new BrowserVideoEncoder({ onBatch, onFailure: vi.fn(), canSend: () => true })
  await client.start(video)
  tick(10)
  await vi.advanceTimersByTimeAsync(30)
  client.resetTransport()
  FakeEncoder.last.emit(10, true)
  await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).not.toHaveBeenCalled()
  tick(150); FakeEncoder.last.emit(150, true)
  await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).toHaveBeenCalledOnce()
  expect(onBatch.mock.calls[0][0].frames[0].timestampMs).toBe(150)
  client.dispose()
})

it('keeps an idle encoder warm through source or transport pauses and resumes real frames', async () => {
  let available = true
  const onBatch = vi.fn(), onFailure = vi.fn()
  const client = new BrowserVideoEncoder({onBatch,onFailure,canSend:()=>available})
  await client.start(video)
  await vi.advanceTimersByTimeAsync(8000)
  expect(onFailure).not.toHaveBeenCalled()
  tick(8000); FakeEncoder.last.emit(8000)
  await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).toHaveBeenCalledOnce()
  available = false
  tick(8100)
  await vi.advanceTimersByTimeAsync(10000)
  expect(onFailure).not.toHaveBeenCalled()
  expect(FakeEncoder.last.close).not.toHaveBeenCalled()
  available = true
  tick(18200)
  // The first new input after an idle period gets its own output deadline.
  await vi.advanceTimersByTimeAsync(200)
  expect(onFailure).not.toHaveBeenCalled()
  FakeEncoder.last.emit(18200)
  await vi.advanceTimersByTimeAsync(100)
  expect(onBatch).toHaveBeenCalledTimes(2)
  client.dispose()
  expect(vi.getTimerCount()).toBe(0)
})
