import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DeviceVision } from './DeviceVision'

class WorkerStub {
  static all: WorkerStub[] = []
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  postMessage = vi.fn()
  terminate = vi.fn()
  constructor() { WorkerStub.all.push(this) }
  emit(data: unknown) { this.onmessage?.({ data }) }
}
const video = { readyState: 4, videoWidth: 1280, videoHeight: 720 } as HTMLVideoElement

beforeEach(() => {
  vi.useFakeTimers()
  WorkerStub.all = []
  vi.stubGlobal('Worker', WorkerStub)
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('device worker lifecycle', () => {
  it('crops the source before resizing and paces expensive inference without a queue', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ close: vi.fn() }))
    const device = new DeviceVision(vi.fn(), vi.fn(), 'right', 'balanced')
    device.start()
    const worker = WorkerStub.all[0]
    worker.emit({ type: 'ready', delegate: 'CPU' })
    await device.capture(video, 100)
    expect(createImageBitmap).toHaveBeenCalledWith(video, 640, 0, 640, 720, expect.objectContaining({ resizeHeight: 640 }))
    worker.emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 300 })
    await device.capture(video, 400)
    expect(createImageBitmap).toHaveBeenCalledTimes(1)
    await device.capture(video, 470)
    expect(createImageBitmap).toHaveBeenCalledTimes(2)
    expect(device.budget.previewSide).toBe(640)
    device.dispose()
  })
  it('uses one GPU pose worker, bounds inference and ignores stale results', async () => {
    const bitmap = { close: vi.fn() }
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap))
    const status = vi.fn(), result = vi.fn(), device = new DeviceVision(status, result)
    device.start()
    const worker = WorkerStub.all[0]
    expect(worker.postMessage).toHaveBeenCalledWith(expect.objectContaining({ task: 'pose', poseDelegate: 'GPU', maxPoses: 10 }))
    worker.emit({ type: 'ready', delegate: 'GPU' })
    await device.capture(video, 100)
    await device.capture(video, 250)
    expect(createImageBitmap).toHaveBeenCalledTimes(1)
    worker.emit({ type: 'pose-result', timestampMs: 99, poses: [], inferenceMs: 12 })
    expect(result).not.toHaveBeenCalled()
    worker.emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 12 })
    expect(result).toHaveBeenCalledWith(expect.objectContaining({ timestampMs: 100, delegate: 'GPU' }))
    device.dispose()
    expect(worker.terminate).toHaveBeenCalledOnce()
  })

  it('reports CPU fallback after a GPU stall and stops after a CPU stall', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ close: vi.fn() }))
    const status = vi.fn(), device = new DeviceVision(status, vi.fn())
    device.start()
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    await device.capture(video, 100)
    await vi.advanceTimersByTimeAsync(5001)
    expect(WorkerStub.all).toHaveLength(2)
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledWith(expect.objectContaining({ poseDelegate: 'CPU' }))
    WorkerStub.all[1].emit({ type: 'ready', delegate: 'CPU' })
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'ready', delegate: 'CPU' }))
    await device.capture(video, 6000)
    await vi.advanceTimersByTimeAsync(10001)
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'error' }))
    expect(WorkerStub.all[1].terminate).toHaveBeenCalledOnce()
  })

  it('releases a bitmap when stopped while capture is still pending', async () => {
    let resolve!: (value: unknown) => void
    vi.stubGlobal('createImageBitmap', vi.fn(() => new Promise(r => { resolve = r })))
    const device = new DeviceVision(vi.fn(), vi.fn())
    device.start()
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    const capture = device.capture(video, 100)
    device.dispose()
    const bitmap = { close: vi.fn() }
    resolve(bitmap)
    await capture
    expect(bitmap.close).toHaveBeenCalledOnce()
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(1)
  })
})
