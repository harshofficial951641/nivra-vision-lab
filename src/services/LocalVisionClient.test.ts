import { afterEach, describe, expect, it, vi } from 'vitest'
import { LocalVisionClient } from './LocalVisionClient'

class FakeSocket {
  static OPEN = 1
  static latest: FakeSocket
  readyState = 1
  onopen = () => {}
  onmessage = (_event: { data: string }) => {}
  onclose = () => {}
  onerror = () => {}
  sent: unknown[] = []
  constructor() { FakeSocket.latest = this }
  send(message: unknown) { this.sent.push(message) }
  close() { this.readyState = 3 }
}

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

async function setup() {
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ready' }) }))
  vi.stubGlobal('OffscreenCanvas', class {
    getContext() { return { drawImage() {} } }
    async convertToBlob() { return { arrayBuffer: async () => new ArrayBuffer(8) } }
  })
  const callbacks = { ready: vi.fn(), result: vi.fn(), error: vi.fn() }
  const client = new LocalVisionClient(callbacks)
  await client.connect()
  FakeSocket.latest.onopen()
  return { client, callbacks, socket: FakeSocket.latest }
}

describe('local AI transport', () => {
  it('keeps only one outstanding frame and closes unused bitmaps', async () => {
    const { client, socket } = await setup()
    const first = { width: 100, height: 100, close: vi.fn() } as unknown as ImageBitmap
    const second = { width: 100, height: 100, close: vi.fn() } as unknown as ImageBitmap
    expect(client.submitFrame(first, null, 100)).toBe(true)
    expect(client.submitFrame(second, null, 200)).toBe(false)
    expect(second.close).toHaveBeenCalled()
    await vi.waitFor(() => expect(socket.sent).toHaveLength(1))
    client.dispose()
  })

  it('rejects late results after a source reset', async () => {
    const { client, callbacks, socket } = await setup()
    client.submitFrame({ width: 100, height: 100, close() {} } as ImageBitmap, null, 100)
    await vi.waitFor(() => expect(socket.sent).toHaveLength(1))
    client.resetStream()
    socket.onmessage({ data: JSON.stringify({ version: 1, backend: 'local-ai', streamId: 0, timestampMs: 100, poses: [], conflict: {} }) })
    expect(callbacks.result).not.toHaveBeenCalled()
    expect(client.isBusy).toBe(false)
    expect(socket.sent).toContain(JSON.stringify({ type: 'reset', streamId: 1 }))
    client.dispose()
  })

  it('reports disconnect rather than silently switching engines', async () => {
    const { client, callbacks, socket } = await setup()
    socket.onclose()
    expect(callbacks.error).toHaveBeenCalledWith(expect.stringContaining('explicitly choose Browser'))
    expect(client.isBusy).toBe(true)
  })
})
