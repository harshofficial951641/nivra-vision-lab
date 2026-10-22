import { afterEach, describe, expect, it, vi } from 'vitest'
import { framePacket } from './contracts'
afterEach(() => vi.unstubAllGlobals())
describe('Camera preview protocol', () => {
  it('advertises32-person processing capacity without stretching preview dimensions', async () => {
    vi.stubGlobal('TextEncoder', class { encode(text: string) { return Uint8Array.from(Array.from(text, c => c.charCodeAt(0))) } })
    const jpeg = { size: 2, arrayBuffer: async () => Uint8Array.from([1, 2]).buffer }
    const drawImage = vi.fn()
    const canvas = { width: 0, height: 0, getContext: () => ({ drawImage }), toBlob: (done: (blob: unknown) => void) => done(jpeg) } as unknown as HTMLCanvasElement
    const video = { videoWidth: 1920, videoHeight: 1080, readyState: 4 } as HTMLVideoElement
    const packet = await framePacket(video, canvas, 123, 960)
    expect(packet).toBeTruthy()
    const size = new DataView(packet!).getUint32(0, true)
    const metadata = JSON.parse(String.fromCharCode(...new Uint8Array(packet!, 4, size)))
    expect(metadata).toEqual({ version: 1, timestampMs: 123, streamId: 0, maxPeople: 32 })
    expect([canvas.width, canvas.height]).toEqual([960, 540])
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 960, 540)
  })
})
