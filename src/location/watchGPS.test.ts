import { afterEach, describe, expect, it, vi } from 'vitest'
import { watchGPS } from './watchGPS'
const point = { latitude: 28, longitude: 77, accuracy: 12 }
type Fix = { coords: typeof point; timestamp: number }
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
function device() {
  let success!: (position: Fix) => void
  let failure!: (error: { code: number }) => void
  const clearWatch = vi.fn()
  const watchPosition = vi.fn((next, error, _options?: PositionOptions) => { success = next; failure = error; return 7 })
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('navigator', { geolocation: { watchPosition, clearWatch } })
  return { emit: (timestamp: number, latitude = 28) => success({ coords: { ...point, latitude }, timestamp }), fail: (code: number) => failure({ code }), watchPosition, clearWatch }
}
describe('Live GPS tracking', () => {
  it('sends the newest fix at ten-second intervals without overlapping writes, then cleans up', async () => {
    vi.useFakeTimers()
    const phone = device()
    let finish!: () => void
    const save = vi.fn().mockReturnValueOnce(new Promise<void>(resolve => { finish = resolve })).mockResolvedValue(undefined)
    const onSaved = vi.fn()
    const stop = watchGPS({ save, onSaved, onError: vi.fn() })
    phone.emit(1000)
    phone.emit(2000, 29)
    phone.emit(3000, 30)
    expect(save).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(15000)
    expect(save).toHaveBeenCalledOnce()
    finish()
    await vi.advanceTimersByTimeAsync(0)
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith({ ...point, latitude: 30, capturedAt: 3000 })
    phone.emit(4000, 31)
    await vi.advanceTimersByTimeAsync(9999)
    expect(save).toHaveBeenCalledTimes(2)
    stop()
    await vi.advanceTimersByTimeAsync(20000)
    phone.emit(5000)
    expect(save).toHaveBeenCalledTimes(2)
    expect(phone.clearWatch).toHaveBeenCalledWith(7)
    expect(phone.watchPosition.mock.calls[0][2]).toEqual({ enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
  })
  it('stops on denied permission and allows a new watcher to retry', async () => {
    const phone = device()
    const onError = vi.fn()
    const save = vi.fn().mockResolvedValue(undefined)
    const stop = watchGPS({ save, onSaved: vi.fn(), onError })
    phone.fail(1)
    phone.emit(1000)
    expect(onError).toHaveBeenCalledWith(expect.stringContaining('permission is blocked'))
    expect(save).not.toHaveBeenCalled()
    expect(phone.clearWatch).toHaveBeenCalledWith(7)
    stop()
    const retryStop = watchGPS({ save, onSaved: vi.fn(), onError })
    phone.emit(2000)
    await Promise.resolve()
    expect(save).toHaveBeenCalledOnce()
    retryStop()
  })
  it('retries a failed write after ten seconds even while the phone stays still', async () => {
    vi.useFakeTimers()
    const phone = device()
    const save = vi.fn().mockRejectedValueOnce(new Error('Offline')).mockResolvedValue(undefined)
    const onSaved = vi.fn()
    const stop = watchGPS({ save, onSaved, onError: vi.fn() })
    phone.emit(1000)
    await vi.advanceTimersByTimeAsync(10000)
    expect(save).toHaveBeenCalledTimes(2)
    expect(onSaved).toHaveBeenCalledOnce()
    stop()
  })
})
