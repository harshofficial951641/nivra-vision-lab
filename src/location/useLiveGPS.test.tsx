import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useLiveGPS } from './useLiveGPS'
const point = { latitude: 28, longitude: 77, accuracy: 10 }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
describe('Live GPS lifecycle', () => {
  it('cleans up restarted watches and stops sharing when the shift is disabled', async () => {
    const callbacks: ((value: { coords: typeof point; timestamp: number }) => void)[] = []
    const clearWatch = vi.fn()
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { watchPosition: (next: typeof callbacks[number]) => { callbacks.push(next); return callbacks.length }, clearWatch } })
    const save = vi.fn().mockResolvedValue(undefined)
    const { rerender, unmount } = renderHook(({ enabled }) => useLiveGPS(enabled, save), {
      initialProps: { enabled: true },
    })
    rerender({ enabled: false })
    rerender({ enabled: true })
    expect(callbacks).toHaveLength(2)
    expect(clearWatch).toHaveBeenCalledWith(1)
    await act(async () => {
      callbacks[0]({ coords: point, timestamp: 1000 })
      callbacks[1]({ coords: point, timestamp: 1000 })
    })
    expect(save).toHaveBeenCalledOnce()
    rerender({ enabled: false })
    expect(clearWatch).toHaveBeenCalledWith(2)
    await act(async () => { callbacks[1]({ coords: point, timestamp: 2000 }) })
    expect(save).toHaveBeenCalledOnce()
    unmount()
  })
  it('serializes a retry behind an outstanding server write', async () => {
    let emit!: (value: { coords: typeof point; timestamp: number }) => void
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { watchPosition: (next: typeof emit) => { emit = next; return 1 }, clearWatch: vi.fn() } })
    let finish!: () => void
    const save = vi.fn().mockReturnValueOnce(new Promise<void>(resolve => { finish = resolve })).mockResolvedValue(undefined)
    const { result, unmount } = renderHook(() => useLiveGPS(true, save))
    await act(async () => { emit({ coords: point, timestamp: 1000 }) })
    expect(save).toHaveBeenCalledOnce()
    act(() => result.current.retry())
    await act(async () => { emit({ coords: point, timestamp: 2000 }) })
    expect(save).toHaveBeenCalledOnce()
    await act(async () => { finish() })
    expect(save).toHaveBeenCalledTimes(2)
    expect(result.current.point?.capturedAt).toBe(2000)
    unmount()
  })
})
