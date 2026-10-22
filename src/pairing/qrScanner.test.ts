import { afterEach, describe, expect, it, vi } from 'vitest'
import { startQRScanner } from './qrScanner'
const { decode } = vi.hoisted(() => ({ decode: vi.fn() }))
vi.mock('@zxing/browser', () => ({ BrowserQRCodeReader: class { decodeFromStream = decode } }))
afterEach(() => { vi.resetAllMocks(); vi.unstubAllGlobals() })
const media = () => { const track = { stop: vi.fn() }; return { track, stream: { getTracks: () => [track] } as unknown as MediaStream } }
describe('QR scanner stream ownership', () => {
  it('requests rear camera without audio and stops tracks when cancelled while decoder setup is pending', async () => {
    const { track, stream } = media()
    const getUserMedia = vi.fn().mockResolvedValue(stream)
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    let finish!: (value: { stop(): void }) => void
    decode.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const controller = new AbortController()
    const result = startQRScanner(document.createElement('video'), vi.fn(), controller.signal)
    await vi.waitFor(() => expect(decode).toHaveBeenCalledOnce())
    expect(getUserMedia).toHaveBeenCalledWith({ video: { facingMode: { ideal: 'environment' } }, audio: false })
    controller.abort()
    expect(track.stop).toHaveBeenCalled()
    const stop = vi.fn(); finish({ stop }); await result
    expect(stop).toHaveBeenCalled()
  })
  it('immediately stops a camera permission result that arrives after cancellation', async () => {
    const { track, stream } = media()
    let finish!: (value: MediaStream) => void
    const getUserMedia = vi.fn().mockReturnValue(new Promise(resolve => { finish = resolve }))
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
    const controller = new AbortController()
    const result = startQRScanner(document.createElement('video'), vi.fn(), controller.signal)
    await vi.waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce())
    controller.abort(); finish(stream); await result
    expect(track.stop).toHaveBeenCalled()
    expect(decode).not.toHaveBeenCalled()
  })
  it('does not pass late decoded frames to the UI after cancellation', async () => {
    const { stream } = media()
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } })
    const done = vi.fn(), stop = vi.fn()
    decode.mockResolvedValue({ stop })
    const controller = new AbortController()
    await startQRScanner(document.createElement('video'), done, controller.signal)
    controller.abort()
    const callback = decode.mock.calls[0][2]
    callback({ getText: () => 'late' }, undefined, { stop })
    expect(done).not.toHaveBeenCalled()
  })
})
