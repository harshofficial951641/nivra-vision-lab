import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Publisher from './Publisher'
import type { DeviceMotion, DeviceResult, DeviceStatus } from './deviceAnalysis'
import type { BrowserVideoOptions } from './browserVideoEncoder'

const encoded = vi.hoisted(() => ({ start: vi.fn(), dispose: vi.fn(), reset: vi.fn(), create: vi.fn(), options: null as BrowserVideoOptions | null }))
vi.mock('./browserVideoEncoder', () => ({ BrowserVideoEncoder: class {
  constructor(options: BrowserVideoOptions) { encoded.options = options; encoded.create() }
  start = encoded.start
  dispose = encoded.dispose
  resetTransport = encoded.reset
} }))

const { api, openSocket, framePacket, capture, dispose, resultCallback, motionCallback, statusCallback, createDetector } = vi.hoisted(() => ({ api: vi.fn(), openSocket: vi.fn(), framePacket: vi.fn(), capture: vi.fn(), dispose: vi.fn(), resultCallback: { current: null as ((result: DeviceResult) => void) | null }, motionCallback: { current: null as ((result: DeviceMotion) => void) | null }, statusCallback: { current: null as ((status: DeviceStatus) => void) | null }, createDetector: vi.fn() }))
vi.mock('./contracts', async importOriginal => ({ ...await importOriginal<typeof import('./contracts')>(), api, framePacket, openSocket }))
vi.mock('./DeviceVision', () => ({ DeviceVision: class {
  budget = { previewSide: 960, previewInterval: 84 }
  capture = capture
  dispose = dispose
  onStatus: (status: DeviceStatus) => void
  constructor(onStatus: (status: DeviceStatus) => void, onResult: (result: DeviceResult) => void, _area: unknown, _profile: unknown, onMotion: (result: DeviceMotion) => void) { createDetector(); this.onStatus = onStatus; resultCallback.current = onResult; motionCallback.current = onMotion; statusCallback.current = onStatus }
  start() { this.onStatus({ state: 'ready', delegate: 'GPU', detail: 'Ready' }) }
} }))
beforeEach(() => {
  encoded.start.mockReset().mockResolvedValue(false); encoded.dispose.mockClear(); encoded.reset.mockClear(); encoded.create.mockClear(); encoded.options = null
  api.mockReset(); openSocket.mockReset(); framePacket.mockReset(); capture.mockClear(); dispose.mockClear(); createDetector.mockClear()
  framePacket.mockReturnValue(new Promise(() => {}))
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
  history.replaceState(null, '', '/')
})

describe('Camera phone GPS pairing', () => {
  it('keeps a pairing link available after a network failure and retries it without another QR', async () => {
    history.replaceState(null, '', '/camera#pair=retry-token')
    api.mockRejectedValueOnce(new Error('Temporary network failure')).mockResolvedValue({ id: 'C1', name: 'Gate camera', building: 'Main', floor: 'Entrance', enabled: true, gps: null })
    await act(async () => { render(<Publisher />) })
    expect(location.hash).toBe('#pair=retry-token')
    expect(screen.getByRole('alert')).toHaveTextContent('Temporary network failure')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Try pairing again' })) })
    expect(location.hash).toBe('')
    expect(api).toHaveBeenNthCalledWith(2, '/camera/pair', 'POST', { token: 'retry-token' })
    expect(screen.getByRole('button', { name: 'Allow camera & start' })).toBeEnabled()
  })
  it('pairs an OS-scanned QR without opening the camera until one explicit tap, and shows live only after an acknowledged frame', async () => {
    history.replaceState(null, '', '/camera#pair=browser-token')
    api.mockResolvedValue({ id: 'C1', name: 'Gate', building: 'Main', floor: '1', gps: null })
    const peer = { readyState: WebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: string }) => void) | null }
    openSocket.mockResolvedValue(peer)
    framePacket.mockResolvedValueOnce(new ArrayBuffer(8)).mockReturnValue(new Promise(() => {}))
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] })
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    await act(async () => { render(<Publisher />) })
    expect(api).toHaveBeenCalledWith('/camera/pair', 'POST', { token: 'browser-token' })
    expect(location.hash).toBe('')
    expect(getUserMedia).not.toHaveBeenCalled()
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    await act(async () => { peer.onmessage?.({ data: '{"type":"ready"}' }) })
    expect(screen.getByText('Connecting to camera wall…')).toBeInTheDocument()
    const timestamp = framePacket.mock.calls[0][2] as number
    await act(async () => { peer.onmessage?.({ data: JSON.stringify({ type: 'accepted', timestampMs: timestamp }) }) })
    expect(screen.getByText('Live', { exact: true })).toBeInTheDocument()
    expect(getUserMedia).toHaveBeenCalledOnce()
  })
  it('explains blocked browser camera access and does not ask for location or connect', async () => {
    api.mockResolvedValue({ id: 'C1', name: 'Gate', gps: null })
    const watchPosition = vi.fn()
    const getUserMedia = vi.fn().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError'))
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia }, geolocation: { watchPosition, clearWatch: vi.fn() } })
    await act(async () => { render(<Publisher />) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    expect(screen.getByRole('alert')).toHaveTextContent('Camera access is blocked. Allow it in your browser settings')
    expect(watchPosition).not.toHaveBeenCalled()
    expect(openSocket).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Allow camera & start' })).toBeEnabled()
  })
  it('offers a fresh QR or code when an old pairing link cannot be redeemed', async () => {
    history.replaceState(null, '', '/camera#pair=expired-token')
    api.mockRejectedValue(new Error('Pairing link expired'))
    await act(async () => { render(<Publisher />) })
    expect(screen.getByRole('link', { name: 'Use a new QR or code' })).toHaveAttribute('href', '/camera?connect=1')
    expect(location.hash).toBe('#pair=expired-token')
  })
  it('opens and closes options with a button or a handle swipe without starting the camera', async () => {
    api.mockResolvedValue({ id: 'C1', name: 'Gate', building: 'Main', floor: '1', gps: null })
    const getUserMedia = vi.fn()
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    await act(async () => { render(<Publisher />) })
    const handle = screen.getByText('Options')
    const panel = handle.closest('details')!
    fireEvent.click(handle)
    expect(panel).toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'Close options' }))
    expect(panel).not.toHaveAttribute('open')
    fireEvent.click(handle)
    fireEvent.touchStart(handle, { touches: [{ clientY: 100 }] })
    fireEvent.touchEnd(handle, { changedTouches: [{ clientY: 180 }] })
    expect(panel).not.toHaveAttribute('open')
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Allow camera & start' })).toBeEnabled()
  })
  it('keeps camera controls available after GPS denial and saves a fresh reading on retry', async () => {
    history.replaceState(null, '', '/camera#pair=camera-token')
    const camera = { id: 'C1', name: 'Gate camera', building: 'Main', floor: 'Entrance', enabled: true, gps: null }
    const gps = { latitude: 28.6139, longitude: 77.209, accuracy: 12, capturedAt: 1000 }
    api.mockImplementation((path: string) => Promise.resolve(path === '/camera/location' ? { ...camera, gps } : camera))
    let fix!: (position: { coords: typeof gps; timestamp: number }) => void
    let fail!: (error: { code: number }) => void
    const clearWatch = vi.fn()
    const watchPosition = vi.fn((success, error) => { fix = success; fail = error; return 9 })
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { watchPosition, clearWatch } })
    await act(async () => { render(<Publisher />) })
    expect(api).toHaveBeenCalledWith('/camera/pair', 'POST', { token: 'camera-token' })
    expect(location.hash).toBe('')
    expect(watchPosition).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('Options'))
    fireEvent.click(screen.getByText('Location · not shared yet'))
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Refresh GPS tracking' })) })
    expect(watchPosition).toHaveBeenCalledOnce()
    act(() => fail({ code: 1 }))
    expect(screen.getByRole('alert')).toHaveTextContent('Location permission is blocked')
    expect(screen.getByRole('button', { name: /Allow camera & start/ })).toBeEnabled()
    expect(api).not.toHaveBeenCalledWith('/camera/location', 'POST', expect.anything())
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry GPS location' })) })
    await act(async () => { fix({ coords: gps, timestamp: gps.capturedAt }) })
    expect(api).toHaveBeenCalledWith('/camera/location', 'POST', gps)
    expect(watchPosition).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: 'Refresh GPS tracking' })).toBeEnabled()
    expect(within(screen.getByRole('region', { name: 'Camera GPS' })).getByRole('status')).toHaveTextContent('28.613900, 77.209000')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('link', { name: 'Open in Google Maps' })).toHaveAttribute('href', expect.stringContaining('query=28.6139%2C77.209'))
  })
  it('stops the camera and closes a ticketed socket that resolves after Stop', async () => {
    const camera = { id: 'C1', name: 'Gate camera', building: 'Main', floor: 'Entrance', enabled: true, gps: null }
    api.mockResolvedValue(camera)
    let finish!: (value: unknown) => void
    openSocket.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const stream = { getTracks: () => [track], getVideoTracks: () => [track] }
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { watchPosition: vi.fn(() => 1), clearWatch: vi.fn() }, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    await act(async () => { render(<Publisher />) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    expect(openSocket).toHaveBeenCalledWith('/camera/stream', { signal: expect.any(AbortSignal) })
    const signal = openSocket.mock.calls[0][1].signal as AbortSignal
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Stop camera' })) })
    expect(signal.aborted).toBe(true)
    const peer = { close: vi.fn() }
    await act(async () => { finish(peer) })
    expect(track.stop).toHaveBeenCalledOnce()
    expect(peer.close).toHaveBeenCalledOnce()
    expect(screen.getByRole('button', { name: 'Allow camera & start' })).toBeEnabled()
  })

  it('keeps analysis sampling and alert delivery moving while preview JPEG work is stalled, then stops both loops', async () => {
    vi.useFakeTimers()
    capture.mockClear()
    dispose.mockClear()
    framePacket.mockReset().mockResolvedValueOnce(new ArrayBuffer(8)).mockReturnValue(new Promise(() => {}))
    const camera = { id: 'C1', name: 'Gate camera', building: 'Main', floor: 'Entrance', enabled: true, gps: null }
    api.mockResolvedValue(camera)
    const peer = { readyState: WebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: string }) => void) | null }
    openSocket.mockResolvedValueOnce(peer)
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const stream = { getTracks: () => [track], getVideoTracks: () => [track] }
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { watchPosition: vi.fn(() => 1), clearWatch: vi.fn() }, mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    const { unmount } = render(<Publisher />)
    await act(async () => {})
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    await act(async () => { peer.onmessage?.({ data: JSON.stringify({ type: 'ready' }) }) })
    await act(async () => { await vi.advanceTimersByTimeAsync(250) })
    expect(framePacket).toHaveBeenCalledTimes(2)
    expect(capture.mock.calls.length).toBeGreaterThanOrEqual(5)
    act(() => peer.onmessage?.({ data: JSON.stringify({ type: 'accepted', timestampMs: framePacket.mock.calls[0][2] }) }))
    const result: DeviceResult = { type: 'device-result', model: 'nivra-browser-motion-v1', delegate: 'GPU', timestampMs: 250, inferenceMs: 20, observedPeople: 2, usablePeople: 2, tracks: [], poses: [], conflict: { status: 'alert', explanation: 'Possible conflict' }, events: [{ id: 'event-1', occurredAtMs: 250, detail: 'Review interaction' }] }
    act(() => { resultCallback.current?.(result) })
    expect(peer.send).toHaveBeenCalledWith(JSON.stringify(result))
    const motion: DeviceMotion = { ...result, type: 'device-motion', timestampMs: 250, events: [{ id: 'fast-event', occurredAtMs: 250, detail: 'Independent motion review' }] }
    act(() => { motionCallback.current?.(motion) })
    expect(peer.send).toHaveBeenCalledWith(JSON.stringify(motion))
    expect(screen.getByRole('region', { name: 'Detection status' })).toHaveTextContent('Review interaction')
    expect(screen.getByText('2 people detected')).toBeInTheDocument()
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Stop camera' })) })
    const callsAfterStop = capture.mock.calls.length
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(capture).toHaveBeenCalledTimes(callsAfterStop)
    expect(dispose).toHaveBeenCalledOnce()
    expect(peer.close).toHaveBeenCalledOnce()
    expect(track.stop).toHaveBeenCalledOnce()
    unmount()
  })

  it('reconnects a lost socket using the same camera stream and cancels retries on Stop', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue({ id: 'C1', name: 'Gate', building: 'Main', floor: '1', gps: null })
    const peer = () => ({ readyState: WebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: string }) => void) | null, onclose: null as (() => void) | null })
    const first = peer(), second = peer()
    openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] })
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    await act(async () => { render(<Publisher />) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    act(() => { first.onmessage?.({ data: '{"type":"ready"}' }) })
    act(() => { first.onclose?.() })
    expect(screen.getByRole('region', { name: 'Detection status' })).toHaveTextContent('Reconnecting camera')
    expect(track.stop).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(500) })
    act(() => { second.onmessage?.({ data: '{"type":"ready"}' }) })
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(openSocket).toHaveBeenCalledTimes(2)
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Stop camera' })) })
    const captures = capture.mock.calls.length
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(openSocket).toHaveBeenCalledTimes(2)
    expect(capture).toHaveBeenCalledTimes(captures)
    expect(track.stop).toHaveBeenCalledOnce()
  })

  it('keeps reconnecting at a bounded rate without asking for camera access again and stops on request', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue({ id: 'C1', name: 'Gate', building: 'Main', floor: '1', gps: null })
    openSocket.mockRejectedValue(new Error('Offline'))
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] })
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    await act(async () => { render(<Publisher />) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(openSocket).toHaveBeenCalledTimes(6)
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(track.stop).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Stop camera' }))
    await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
    expect(openSocket).toHaveBeenCalledTimes(6)
    expect(track.stop).toHaveBeenCalledOnce()
  })

  it('retries detection without reopening the camera or reconnecting its socket', async () => {
    vi.useFakeTimers()
    api.mockResolvedValue({ id: 'C1', name: 'Gate', building: 'Main', floor: '1', gps: null })
    const peer = { readyState: WebSocket.OPEN, bufferedAmount: 0, send: vi.fn(), close: vi.fn(), onmessage: null as ((event: { data: string }) => void) | null }
    openSocket.mockResolvedValue(peer)
    const track = { stop: vi.fn(), addEventListener: vi.fn() }
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track], getVideoTracks: () => [track] })
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
    await act(async () => { render(<Publisher />) })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Allow camera & start' })) })
    act(() => { peer.onmessage?.({ data: '{"type":"ready"}' }) })
    act(() => { statusCallback.current?.({ state: 'error', delegate: null, detail: 'Model unavailable' }) })
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Retry detection' })) })
    expect(dispose).toHaveBeenCalledOnce()
    expect(track.stop).not.toHaveBeenCalled()
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(openSocket).toHaveBeenCalledOnce()
  })

})

describe('camera LAN recovery',()=>{
  it('connects and retries despite an offline network hint, preserves a healthy peer, and never restarts after Stop',async()=>{
    vi.useFakeTimers()
    api.mockResolvedValue({id:'C1',name:'Gate',gps:null})
    const makePeer=()=>({readyState:WebSocket.OPEN,bufferedAmount:0,send:vi.fn(),close:vi.fn(),onclose:null as (()=>void)|null,onmessage:null as ((event:{data:string})=>void)|null})
    const first=makePeer(),second=makePeer()
    openSocket.mockResolvedValueOnce(first).mockResolvedValueOnce(second)
    const track={stop:vi.fn(),addEventListener:vi.fn()}
    const getUserMedia=vi.fn().mockResolvedValue({getTracks:()=>[track],getVideoTracks:()=>[track]})
    vi.stubGlobal('isSecureContext',true)
    vi.stubGlobal('navigator',{onLine:false,mediaDevices:{getUserMedia}})
    vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue()
    await act(async()=>{render(<Publisher />)})
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Allow camera & start'}))})
    expect(openSocket).toHaveBeenCalledOnce()
    act(()=>first.onmessage?.({data:'{"type":"ready"}'}))
    const disposed=dispose.mock.calls.length
    await act(async()=>{window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'))})
    expect(first.close).not.toHaveBeenCalled()
    expect(dispose).toHaveBeenCalledTimes(disposed)
    act(()=>first.onclose?.())
    await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
    expect(openSocket).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole('button',{name:'Stop camera'}))
    await act(async()=>{window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'));await vi.advanceTimersByTimeAsync(20000)})
    expect(openSocket).toHaveBeenCalledTimes(2)
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(track.stop).toHaveBeenCalledOnce()
  })
})

describe('camera-session detector lifetime',()=>{
  it('recovers JPEG fallback after a hung preview capture and a failed encoder without restarting detection',async()=>{
    vi.useFakeTimers();encoded.start.mockResolvedValue(true)
    api.mockResolvedValue({id:'C1',name:'Gate',gps:null})
    framePacket.mockReturnValueOnce(new Promise(()=>{})).mockResolvedValue(new ArrayBuffer(8))
    const peer={readyState:WebSocket.OPEN,bufferedAmount:0,send:vi.fn(),close:vi.fn(),onmessage:null as ((event:{data:string})=>void)|null}
    openSocket.mockResolvedValue(peer)
    const track={stop:vi.fn(),addEventListener:vi.fn()}
    vi.stubGlobal('isSecureContext',true)
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockResolvedValue({getTracks:()=>[track],getVideoTracks:()=>[track]})}})
    vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue()
    await act(async()=>render(<Publisher />))
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Allow camera & start'})))
    await act(async()=>peer.onmessage?.({data:'{"type":"ready","browserVideo":true}'}))
    await act(async()=>peer.onmessage?.({data:'{"type":"browser-video-ready","version":1}'}))
    act(()=>encoded.options!.onFailure())
    await act(async()=>{await vi.advanceTimersByTimeAsync(1501)})
    expect(framePacket.mock.calls.length).toBeGreaterThanOrEqual(2)
    const stamp=framePacket.mock.calls.at(-1)![2]
    act(()=>peer.onmessage?.({data:JSON.stringify({type:'accepted',timestampMs:stamp})}))
    expect(screen.getByText('Live',{exact:true})).toBeInTheDocument()
    expect(openSocket).toHaveBeenCalledOnce();expect(createDetector).toHaveBeenCalledOnce()
    expect(peer.close).not.toHaveBeenCalled();expect(track.stop).not.toHaveBeenCalled()
  })
  it('negotiates fast video, keeps its encoder warm across reconnects, and ignores output after Stop',async()=>{
    vi.useFakeTimers();encoded.start.mockResolvedValue(true)
    api.mockResolvedValue({id:'C1',name:'Gate',gps:null})
    framePacket.mockResolvedValue(new ArrayBuffer(8))
    const peers=Array.from({length:2},()=>({readyState:WebSocket.OPEN,bufferedAmount:0,send:vi.fn(),close:vi.fn(),onmessage:null as ((event:{data:string})=>void)|null,onclose:null as (()=>void)|null}))
    peers.forEach(peer=>openSocket.mockResolvedValueOnce(peer))
    const track={stop:vi.fn(),addEventListener:vi.fn()}
    vi.stubGlobal('isSecureContext',true)
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia:vi.fn().mockResolvedValue({getTracks:()=>[track],getVideoTracks:()=>[track]})}})
    vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue()
    await act(async()=>render(<Publisher />))
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Allow camera & start'})))
    await act(async()=>peers[0].onmessage?.({data:'{"type":"ready","browserVideo":true}'}))
    expect(peers[0].send).toHaveBeenCalledWith('{"type":"browser-video-hello","version":1}')
    expect(encoded.start).not.toHaveBeenCalled()
    await act(async()=>peers[0].onmessage?.({data:'{"type":"browser-video-ready","version":1}'}))
    expect(encoded.start).toHaveBeenCalledOnce()
    const batch={type:'browser-video-v1' as const,version:1 as const,generation:'v1',codec:'avc1.42002a',description:'config',width:1280,height:720,frames:[{sequence:1,timestampMs:10,keyframe:true,data:'frame'}]}
    act(()=>encoded.options!.onBatch(batch))
    expect(peers[0].send).toHaveBeenCalledWith(JSON.stringify(batch))
    act(()=>peers[0].onmessage?.({data:'{"type":"video-accepted","timestampMs":10}'}))
    expect(screen.getByText('Live',{exact:true})).toBeInTheDocument()
    act(()=>peers[0].onclose?.())
    expect(encoded.options!.canSend()).toBe(false)
    await act(async()=>{await vi.advanceTimersByTimeAsync(500)})
    await act(async()=>peers[1].onmessage?.({data:'{"type":"ready","browserVideo":true}'}))
    await act(async()=>peers[1].onmessage?.({data:'{"type":"browser-video-ready","version":1}'}))
    expect(encoded.create).toHaveBeenCalledOnce();expect(encoded.start).toHaveBeenCalledOnce()
    expect(encoded.reset).toHaveBeenCalledTimes(2)
    expect(createDetector).toHaveBeenCalledOnce()
    act(()=>encoded.options!.onBatch({...batch,generation:'v2',frames:[{...batch.frames[0],sequence:2,timestampMs:600}]}))
    expect(peers[1].send).toHaveBeenCalledWith(expect.stringContaining('"generation":"v2"'))
    act(()=>fireEvent.click(screen.getByRole('button',{name:'Stop camera'})))
    const sent=peers[1].send.mock.calls.length
    act(()=>encoded.options!.onBatch(batch))
    expect(peers[1].send).toHaveBeenCalledTimes(sent)
    expect(encoded.dispose).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('keeps one Full detector and one capture loop across three reconnects, gates new peers until ready, and disposes on Stop',async()=>{
    vi.useFakeTimers()
    api.mockResolvedValue({id:'C1',name:'Gate',gps:null})
    framePacket.mockResolvedValue(new ArrayBuffer(8))
    const peers=Array.from({length:5},()=>({readyState:WebSocket.OPEN,bufferedAmount:0,send:vi.fn(),close:vi.fn(),onmessage:null as ((event:{data:string})=>void)|null,onclose:null as ((event?:{code:number})=>void)|null}))
    peers.forEach(peer=>openSocket.mockResolvedValueOnce(peer))
    const track={stop:vi.fn(),addEventListener:vi.fn()}
    const getUserMedia=vi.fn().mockResolvedValue({getTracks:()=>[track],getVideoTracks:()=>[track]})
    vi.stubGlobal('isSecureContext',true)
    vi.stubGlobal('navigator',{mediaDevices:{getUserMedia}})
    vi.spyOn(HTMLMediaElement.prototype,'play').mockResolvedValue()
    const makeResult=(id:string):DeviceResult=>({type:'device-result',model:'nivra-browser-motion-v1',delegate:'GPU',timestampMs:performance.now(),inferenceMs:20,observedPeople:2,usablePeople:2,tracks:[],poses:[],conflict:{status:'clear',explanation:'Observed'},events:[{id,occurredAtMs:performance.now(),detail:'Review'}]})
    await act(async()=>{render(<Publisher />)})
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Allow camera & start'})))
    act(()=>peers[0].onmessage?.({data:'{"type":"ready"}'}))
    expect(createDetector).toHaveBeenCalledOnce()
    for(let round=0;round<3;round++){
      const prior=peers[round],next=peers[round+1]
      act(()=>prior.onclose?.())
      const captures=capture.mock.calls.length,priorMessages=prior.send.mock.calls.length
      await act(async()=>{await vi.advanceTimersByTimeAsync([500,1500,3000][round])})
      expect(capture.mock.calls.length - captures).toBe([10,30,60][round])
      act(()=>resultCallback.current?.(makeResult(`disconnected-${round}`)))
      expect(prior.send).toHaveBeenCalledTimes(priorMessages)
      expect(next.send).not.toHaveBeenCalled()
      act(()=>next.onmessage?.({data:'{"type":"ready"}'}))
      expect(next.send.mock.calls.filter(call=>typeof call[0]==='string').map(call=>call[0])).toEqual([JSON.stringify({type:'device-status',state:'ready',delegate:'GPU',detail:'Ready'})])
      await act(async()=>{await vi.advanceTimersByTimeAsync(50)})
      const fresh=makeResult(`fresh-${round}`)
      act(()=>resultCallback.current?.({...fresh,events:[...fresh.events,{id:`stale-${round}`,occurredAtMs:performance.now()-6000,detail:'Expired'}]}))
      expect(JSON.parse(next.send.mock.calls.find(call=>typeof call[0]==='string')![0]).type).toBe('device-status')
      expect(next.send.mock.calls.filter(call=>typeof call[0]==='string')).toHaveLength(1)
      act(()=>next.onmessage?.({data:JSON.stringify({type:'accepted',timestampMs:framePacket.mock.calls.at(-1)![2]})}))
      expect(next.send).toHaveBeenLastCalledWith(JSON.stringify(fresh))
      expect(prior.send).toHaveBeenCalledTimes(priorMessages)
      expect(createDetector).toHaveBeenCalledOnce()
      expect(dispose).not.toHaveBeenCalled()
    }
    // A sustained healthy connection resets historical backoff; READY alone
    // above did not reset the500/1500/3000ms reconnect progression.
    for(let i=0;i<29;i++){
      await act(async()=>{await vi.advanceTimersByTimeAsync(84)})
      act(()=>peers[3].onmessage?.({data:JSON.stringify({type:'accepted',timestampMs:framePacket.mock.calls.at(-1)![2]})}))
    }
    act(()=>peers[3].onclose?.())
    await act(async()=>{await vi.advanceTimersByTimeAsync(499)})
    expect(openSocket).toHaveBeenCalledTimes(4)
    await act(async()=>{await vi.advanceTimersByTimeAsync(1)})
    expect(openSocket).toHaveBeenCalledTimes(5)
    act(()=>peers[4].onmessage?.({data:'{"type":"ready"}'}))
    expect(createDetector).toHaveBeenCalledOnce()
    expect(getUserMedia).toHaveBeenCalledOnce()
    act(()=>fireEvent.click(screen.getByRole('button',{name:'Stop camera'})))
    const captures=capture.mock.calls.length,messages=peers[4].send.mock.calls.length
    act(()=>resultCallback.current?.(makeResult('after-stop')))
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000)})
    expect(capture).toHaveBeenCalledTimes(captures)
    expect(peers[4].send).toHaveBeenCalledTimes(messages)
    expect(dispose).toHaveBeenCalledOnce()
    expect(track.stop).toHaveBeenCalledOnce()
  })
})
