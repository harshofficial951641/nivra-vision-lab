import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useClassroom } from './useClassroom'
const { api, openSocket, authenticateSocket } = vi.hoisted(() => ({ api: vi.fn(), openSocket: vi.fn(), authenticateSocket: vi.fn() }))
vi.mock('./contracts', () => ({ api, openSocket }))
vi.mock('../auth/session', () => ({ authenticateSocket }))
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('async operator socket lifecycle', () => {
  it('closes a socket whose ticket resolves after unmount without authenticating or reconnecting', async () => {
    let finish!: (socket: unknown) => void
    openSocket.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const hook = renderHook(() => useClassroom(true, undefined, true))
    hook.unmount()
    const peer = { close: vi.fn() }
    await act(async () => { finish(peer) })
    expect(peer.close).toHaveBeenCalledOnce()
    expect(authenticateSocket).not.toHaveBeenCalled()
  })
  it('authenticates the resolved socket and releases it when disabled', async () => {
    const peer = { close: vi.fn() }
    openSocket.mockResolvedValueOnce(peer)
    const hook = renderHook(({ enabled }) => useClassroom(enabled, undefined, true), { initialProps: { enabled: true } })
    await act(async () => {})
    expect(openSocket).toHaveBeenCalledWith('/operator')
    expect(authenticateSocket).toHaveBeenCalledWith(peer)
    hook.rerender({ enabled: false })
    expect(peer.close).toHaveBeenCalledOnce()
  })
})

describe('Aligned analysis previews', () => {
  it('keeps the live JPEG smooth, selects the old matching source, and revokes both URL lifetimes on generation change', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(10000)
    let count = 0
    const created = vi.fn(() => `blob:${++count}`)
    const revoked = vi.fn()
    const OriginalURL = URL
    vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = created; static revokeObjectURL = revoked })
    vi.stubGlobal('TextEncoder', class { encode(text: string) { return Uint8Array.from(Array.from(text, char => char.charCodeAt(0))) } })
    vi.stubGlobal('TextDecoder', class { decode(bytes: ArrayBuffer) { return String.fromCharCode(...new Uint8Array(bytes)) } })
    const peer = { close: vi.fn(), onmessage: null as ((event: { data: string | ArrayBuffer }) => void) | null }
    openSocket.mockResolvedValueOnce(peer)
    const hook = renderHook(() => useClassroom(true, undefined, true))
    await act(async () => {})
    const snapshot = (generation: string) => JSON.stringify({ version: 3, type: 'snapshot', cameras: [{ id: 'c1', feed: 'live', generation, result: { timestampMs: 100, inferenceMs: 1700 } }], events: [] })
    const packet = (timestampMs: number) => {
      const header = new TextEncoder().encode(JSON.stringify({ cameraId: 'c1', generation: 'g1', timestampMs, width: 640, height: 360 }))
      const data = new Uint8Array(4 + header.length + 2)
      new DataView(data.buffer).setUint32(0, header.length, true)
      data.set(header, 4)
      data.set([1, 2], 4 + header.length)
      return data.buffer
    }
    act(() => { peer.onmessage?.({ data: snapshot('g1') }); peer.onmessage?.({ data: packet(100) }) })
    await act(async () => { await vi.advanceTimersByTimeAsync(80) })
    const firstAnalysis = hook.result.current.analysisPreviews.c1
    const firstLive = hook.result.current.previews.c1
    expect(firstAnalysis).toMatchObject({ timestampMs: 100, analysisFrame: true })
    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    act(() => { peer.onmessage?.({ data: packet(1800) }) })
    await act(async () => { await vi.advanceTimersByTimeAsync(80) })
    expect(hook.result.current.previews.c1.timestampMs).toBe(1800)
    expect(hook.result.current.analysisPreviews.c1.url).toBe(firstAnalysis.url)
    expect(revoked).toHaveBeenCalledWith(firstLive.url)
    expect(revoked).not.toHaveBeenCalledWith(firstAnalysis.url)
    act(() => { peer.onmessage?.({ data: snapshot('g2') }) })
    expect(hook.result.current.previews).toEqual({})
    expect(hook.result.current.analysisPreviews).toEqual({})
    hook.unmount()
    expect(revoked).toHaveBeenCalledTimes(created.mock.calls.length)
    expect(new Set(revoked.mock.calls.map(call => call[0])).size).toBe(created.mock.calls.length)
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })
})

const state = (name = 'Current') => ({ version: 3, type: 'snapshot', cameras: [], events: [], site: { id: 's', name } })
const peer = () => ({ close: vi.fn(), onopen: null as (() => void) | null, onclose: null as ((event: { code: number; reason?: string }) => void) | null, onerror: null as (() => void) | null, onmessage: null as ((event: { data: string }) => void) | null })
describe('operator connection recovery', () => {
  it('keeps HTTP setup available without calling an unauthenticated open socket connected', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue(state())
    const first = peer(), second = peer()
    openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const hook = renderHook(() => useClassroom(true, undefined, true))
    await act(async () => {})
    act(() => first.onopen?.())
    expect(hook.result.current.connection).toBe('connecting')
    expect(hook.result.current.apiAvailable).toBe(true)
    expect(hook.result.current.snapshot?.site?.name).toBe('Current')
    const late = first.onmessage!
    await act(async () => { await vi.advanceTimersByTimeAsync(12000) })
    expect(first.close).toHaveBeenCalledOnce()
    expect(hook.result.current.connection).toBe('disconnected')
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    act(() => second.onmessage?.({ data: JSON.stringify(state('Fresh')) }))
    expect(hook.result.current.connection).toBe('connected')
    act(() => late({ data: JSON.stringify(state('Old channel')) }))
    expect(hook.result.current.snapshot?.site?.name).toBe('Fresh')
  })
  it('does not replace a newer authenticated snapshot with an older HTTP fallback and aborts fallback on unmount', async () => {
    let finish!: (value: unknown) => void
    let signal!: AbortSignal
    api.mockImplementation((_path, _method, _body, options) => { signal = options.signal; return new Promise(resolve => { finish = resolve }) })
    const socket = peer(); openSocket.mockResolvedValue(socket)
    const hook = renderHook(() => useClassroom(true, undefined, true))
    await act(async () => {})
    act(() => socket.onmessage?.({ data: JSON.stringify(state('New live state')) }))
    await act(async () => finish(state('Old HTTP state')))
    expect(hook.result.current.snapshot?.site?.name).toBe('New live state')
    hook.unmount()
    expect(signal.aborted).toBe(true)
  })
  it('recovers immediately when the network returns and removes recovery listeners on unmount', async () => {
    vi.useFakeTimers(); api.mockResolvedValue(state())
    const first = peer(), second = peer(); openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const hook = renderHook(() => useClassroom(true, undefined, true))
    await act(async () => {})
    await act(async () => { window.dispatchEvent(new Event('online')) })
    expect(first.close).toHaveBeenCalledOnce()
    expect(openSocket).toHaveBeenCalledTimes(2)
    act(() => second.onmessage?.({ data: JSON.stringify(state()) }))
    expect(hook.result.current.connection).toBe('connected')
    hook.unmount()
    window.dispatchEvent(new Event('online'))
    expect(openSocket).toHaveBeenCalledTimes(2)
  })
})
