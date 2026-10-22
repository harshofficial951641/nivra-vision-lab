import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CrowdPoseVision, RTMO_T_MODEL } from './CrowdPoseVision'

class WorkerStub {
  static last: WorkerStub
  onmessage: ((event: {data: unknown}) => void) | null = null
  onerror: (() => void) | null = null
  postMessage = vi.fn()
  terminate = vi.fn()
  constructor() { WorkerStub.last = this }
  emit(data: unknown) { this.onmessage?.({data}) }
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('Worker', WorkerStub)
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('allows cold loading past30 seconds and cancels the90 second deadline when ready', async () => {
  const client = new CrowdPoseVision(RTMO_T_MODEL)
  const started = client.start()
  await vi.advanceTimersByTimeAsync(45000)
  expect(WorkerStub.last.terminate).not.toHaveBeenCalled()
  expect(console.warn).not.toHaveBeenCalled()
  WorkerStub.last.emit({type:'ready',delegate:'CPU'})
  await expect(started).resolves.toBeUndefined()
  await vi.advanceTimersByTimeAsync(90000)
  expect(WorkerStub.last.terminate).not.toHaveBeenCalled()
  client.dispose()
  expect(vi.getTimerCount()).toBe(0)
})

it('terminates a permanently stalled cold load at90 seconds with only a categorical warning', async () => {
  const client = new CrowdPoseVision(RTMO_T_MODEL)
  const failed = expect(client.start()).rejects.toThrow('Crowd model loading timed out.')
  await vi.advanceTimersByTimeAsync(89999)
  expect(WorkerStub.last.terminate).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  await failed
  expect(WorkerStub.last.terminate).toHaveBeenCalledOnce()
  expect(console.warn).toHaveBeenCalledExactlyOnceWith('[NIVRA crowd detection]','loading-timeout')
  expect(vi.getTimerCount()).toBe(0)
})

it('Stop cancels a slow load, rejects its waiter, and ignores late worker readiness', async () => {
  const client = new CrowdPoseVision(RTMO_T_MODEL)
  const stopped = expect(client.start()).rejects.toThrow('Crowd detection stopped.')
  await vi.advanceTimersByTimeAsync(45000)
  client.dispose()
  await stopped
  WorkerStub.last.emit({type:'ready',delegate:'CPU'})
  await vi.advanceTimersByTimeAsync(100000)
  expect(WorkerStub.last.terminate).toHaveBeenCalledOnce()
  expect(console.warn).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})
