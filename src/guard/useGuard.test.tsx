import { StrictMode, type ReactNode } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useGuard } from './useGuard'

const { api, openSocket, authenticateSocket } = vi.hoisted(() => ({ api: vi.fn(), openSocket: vi.fn(), authenticateSocket: vi.fn() }))
vi.mock('../classroom/contracts', () => ({ api, openSocket }))
vi.mock('../auth/session', () => ({ authenticateSocket }))
beforeEach(() => { openSocket.mockImplementation(async (path: string) => new WebSocket(`ws://localhost${path}`)) })
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  sessionStorage.clear()
  api.mockReset()
  vi.useRealTimers()
  openSocket.mockReset()
  authenticateSocket.mockClear()
  history.replaceState(null, '', '/')
})

describe('Guard QR pairing', () => {
  it('redeems a single-use QR once under StrictMode and opens the stream only after redemption', async () => {
    let redeem!: (value: unknown) => void
    api.mockReturnValueOnce(new Promise(resolve => { redeem = resolve }))
    const sockets: FakeSocket[] = []
    class FakeSocket {
      onopen: (() => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: ((event: { code: number }) => void) | null = null
      close = vi.fn()
      url: string
      constructor(url: string) { this.url = url; sockets.push(this) }
    }
    vi.stubGlobal('WebSocket', FakeSocket)
    history.replaceState(null, '', '/guard#pair=one-use-token-01234567890123456789')
    const { result, unmount } = renderHook(() => useGuard(false, null), {
      wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
    })
    expect(api).toHaveBeenCalledExactlyOnceWith('/guard/pair', 'POST', { token: 'one-use-token-01234567890123456789' }, { timeoutMs: 10000 })
    expect(location.hash).toBe('')
    expect(sockets).toHaveLength(0)
    await act(async () => { redeem({ guard: 'G1' }) })
    expect(sockets).toHaveLength(1)
    expect(authenticateSocket).toHaveBeenCalledExactlyOnceWith(sockets[0])
    act(() => {
      sockets[0].onopen?.()
      sockets[0].onmessage?.({ data: JSON.stringify({ type: 'guard-snapshot', guard: { callsign: 'G1', name: 'Guard one', shift: 'on_shift' }, alerts: [] }) })
    })
    expect(result.current.connection).toBe('connected')
    expect(result.current.view?.callsign).toBe('G1')
    unmount()
    expect(sockets[0].close).toHaveBeenCalledOnce()
  })
  it('redeems a short-lived pairing token retained through Clerk hash sign-in', async () => {
    api.mockResolvedValueOnce({ guard: 'G2' })
    const close = vi.fn()
    vi.stubGlobal('WebSocket', class { close = close })
    history.replaceState(null, '', '/guard')
    const token = 'clerk-pending-token-01234567890123456789'
    sessionStorage.setItem('nivra.guard.pendingPair', JSON.stringify({ token, expiresAt: Date.now() + 300000 }))
    await act(async () => { renderHook(() => useGuard(false, null), {
      wrapper: ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>,
    }) })
    expect(api).toHaveBeenCalledExactlyOnceWith('/guard/pair', 'POST', { token }, { timeoutMs: 10000 })
    expect(sessionStorage.getItem('nivra.guard.pendingPair')).toBeNull()
    expect(location.search).toBe('')
  })

  it('closes an asynchronously ticketed socket that arrives after the guard screen unmounts', async () => {
    let finish!: (value: unknown) => void
    openSocket.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    api.mockResolvedValueOnce({ guard: 'G2' })
    history.replaceState(null, '', '/guard')
    const hook = renderHook(() => useGuard(false, null))
    await act(async () => {})
    expect(openSocket).toHaveBeenCalledWith('/guard/stream', { signal: expect.any(AbortSignal) })
    const signal = openSocket.mock.calls[0][1].signal as AbortSignal
    hook.unmount()
    expect(signal.aborted).toBe(true)
    const peer = { close: vi.fn() }
    await act(async () => { finish(peer) })
    expect(peer.close).toHaveBeenCalledOnce()
    expect(authenticateSocket).not.toHaveBeenCalled()
  })

})

const guardPeer = () => ({ close: vi.fn(), send: vi.fn(), readyState: 1,
  onopen: null as (() => void) | null, onerror: null as (() => void) | null,
  onmessage: null as ((event: { data: string }) => void) | null,
  onclose: null as ((event: { code: number }) => void) | null })
const guardSnapshot = (name = 'Guard') => JSON.stringify({ type: 'guard-snapshot', guard: { callsign: 'G1', name, shift: 'on_shift' }, alerts: [] })
describe('guard connection recovery', () => {
  it('requires a valid snapshot, retries a silent handshake, and rejects callbacks from the old channel', async () => {
    vi.useFakeTimers(); api.mockResolvedValue({ guard: 'G1' })
    const first = guardPeer(), second = guardPeer()
    openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const hook = renderHook(() => useGuard(false, null))
    await act(async () => {})
    act(() => first.onopen?.())
    expect(hook.result.current.connection).toBe('connecting')
    const old = first.onmessage!
    await act(async () => { await vi.advanceTimersByTimeAsync(13000) })
    expect(first.close).toHaveBeenCalledOnce()
    act(() => second.onmessage?.({ data: guardSnapshot('Current guard') }))
    expect(hook.result.current.connection).toBe('connected')
    act(() => old({ data: guardSnapshot('Old guard') }))
    expect(hook.result.current.view?.name).toBe('Current guard')
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(second.send).toHaveBeenCalledWith('ping')
  })
  it('reports malformed updates and reconnects immediately on network return without keeping stale channels', async () => {
    vi.useFakeTimers(); api.mockResolvedValue({ guard: 'G1' })
    const first = guardPeer(), second = guardPeer()
    openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const hook = renderHook(() => useGuard(false, null))
    await act(async () => {})
    act(() => first.onmessage?.({ data: 'not json' }))
    expect(hook.result.current.problem).toContain('Could not read')
    expect(hook.result.current.connection).toBe('disconnected')
    await act(async () => { window.dispatchEvent(new Event('online')) })
    expect(openSocket).toHaveBeenCalledTimes(2)
    act(() => second.onmessage?.({ data: guardSnapshot() }))
    expect(hook.result.current.connection).toBe('connected')
    hook.unmount()
    await act(async () => { window.dispatchEvent(new Event('online')); await vi.advanceTimersByTimeAsync(30000) })
    expect(openSocket).toHaveBeenCalledTimes(2)
    expect(second.close).toHaveBeenCalledOnce()
  })
})

describe('healthy guard resume',()=>{
  it('keeps recent authenticated updates on the same open channel when returning to the page',async()=>{
    vi.useFakeTimers();api.mockResolvedValue({guard:'G1'})
    const socket={...guardPeer(),readyState:1};openSocket.mockResolvedValue(socket)
    const hook=renderHook(()=>useGuard(false,null))
    await act(async()=>{})
    act(()=>socket.onmessage?.({data:guardSnapshot()}))
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000);window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'))})
    expect(openSocket).toHaveBeenCalledOnce()
    expect(socket.close).not.toHaveBeenCalled()
    expect(hook.result.current.connection).toBe('connected')
    hook.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
