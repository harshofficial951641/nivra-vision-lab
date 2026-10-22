import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PeopleVision } from './PeopleVision'
class WorkerStub {
  static all: WorkerStub[] = []
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  onmessageerror: (() => void) | null = null
  postMessage = vi.fn()
  terminate = vi.fn()
  constructor() { WorkerStub.all.push(this) }
  emit(data: unknown) { this.onmessage?.({ data }) }
}
const image = () => ({ close: vi.fn() }) as unknown as ImageBitmap
beforeEach(() => { vi.useFakeTimers(); WorkerStub.all = []; vi.stubGlobal('Worker', WorkerStub) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
describe('Person worker client', () => {
  it('shares initialization, transfers one image, and resolves only its matching frame', async () => {
    const client = new PeopleVision()
    const ready = client.start()
    expect(client.start()).toBe(ready)
    const worker = WorkerStub.all[0]
    expect(worker.postMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'init', modelPath: '/models/efficientdet_lite0_float16.tflite' }))
    worker.emit({ type: 'ready' })
    await ready
    const first = image()
    const result = client.analyze(first, 100)
    expect(worker.postMessage).toHaveBeenLastCalledWith({ type: 'frame', bitmap: first, timestampMs: 100 }, [first])
    const extra = image()
    await expect(client.analyze(extra, 200)).rejects.toThrow('already processing')
    expect(extra.close).toHaveBeenCalledOnce()
    let settled = false
    void result.then(() => { settled = true })
    worker.emit({ type: 'people-result', result: { timestampMs: 99, inferenceMs: 20, people: [] } })
    await Promise.resolve()
    expect(settled).toBe(false)
    const people = Array.from({ length: 32 }, (_, i) => ({ box: [i / 32, 0, (i + 1) / 32, 1], score: .8 }))
    worker.emit({ type: 'people-result', result: { timestampMs: 100, inferenceMs: 200, people } })
    await expect(result).resolves.toMatchObject({ timestampMs: 100, people })
    client.dispose()
    expect(worker.terminate).toHaveBeenCalledOnce()
  })
  it('releases images before readiness and rejects outstanding work on stop', async () => {
    const client = new PeopleVision()
    const early = image()
    await expect(client.analyze(early, 0)).rejects.toThrow('not ready')
    expect(early.close).toHaveBeenCalledOnce()
    const start = client.start()
    WorkerStub.all[0].emit({ type: 'ready' })
    await start
    const pending = client.analyze(image(), 100)
    const assertion = expect(pending).rejects.toThrow('stopped')
    client.dispose()
    await assertion
  })
  it('times out initialization and stalled frame processing without a queue', async () => {
    const client = new PeopleVision()
    const start = client.start()
    const rejected = expect(start).rejects.toThrow('loading timed out')
    await vi.advanceTimersByTimeAsync(30000)
    await rejected
    expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
    const next = new PeopleVision()
    const ready = next.start()
    WorkerStub.all[1].emit({ type: 'ready' })
    await ready
    const result = next.analyze(image(), 200)
    const stalled = expect(result).rejects.toThrow('stalled')
    await vi.advanceTimersByTimeAsync(10000)
    await stalled
    expect(WorkerStub.all[1].terminate).toHaveBeenCalledOnce()
  })
  it('closes an image and rejects cleanly when transfer fails', async () => {
    const client = new PeopleVision()
    const ready = client.start()
    const worker = WorkerStub.all[0]
    worker.emit({ type: 'ready' })
    await ready
    worker.postMessage.mockImplementationOnce(() => { throw new Error('Transfer failed') })
    const bitmap = image()
    await expect(client.analyze(bitmap, 1)).rejects.toThrow('Transfer failed')
    expect(bitmap.close).toHaveBeenCalledOnce()
    expect(worker.terminate).toHaveBeenCalledOnce()
  })
})
