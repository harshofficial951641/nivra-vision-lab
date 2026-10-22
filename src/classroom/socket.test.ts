import { afterEach, describe, expect, it, vi } from 'vitest'
import { openSocket } from './contracts'

const ticket = 'opaque-one-use-01234567890123456789'
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })

function socketStub() {
  const construct = vi.fn()
  vi.stubGlobal('WebSocket', class { constructor(url: string, protocols?: string[]) { construct(url, protocols) } })
  return construct
}

describe('socket factory', () => {
  it('keeps local sockets on the current origin without requesting a ticket', async () => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '')
    const construct = socketStub(), fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await openSocket('/operator')
    expect(construct).toHaveBeenCalledExactlyOnceWith(`ws://${location.host}/api/v2/operator`, undefined)
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each([['/operator', '/operator/socket-ticket'], ['/camera/stream', '/camera/socket-ticket'], ['/guard/stream', '/guard/socket-ticket']])('requests a fresh scoped ticket for %s', async (path, endpoint) => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
    const construct = socketStub()
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ url: `wss://relay.example/api/v2${path}`, ticket }) })
    vi.stubGlobal('fetch', fetch)
    await openSocket(path)
    await openSocket(path)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch).toHaveBeenCalledWith(`/api/v2${endpoint}`, expect.objectContaining({ method: 'POST', credentials: 'same-origin', body: '{}' }))
    expect(construct).toHaveBeenCalledWith(`wss://relay.example/api/v2${path}`, [`nivra-ticket.${ticket}`])
    expect(construct.mock.calls.every(([url]) => !url.includes(ticket))).toBe(true)
  })
  it.each(['ws://relay.example/api/v2/operator', 'wss://relay.example/api/v2/guard/stream', 'wss://relay.example/api/v2/operator?token=secret'])('rejects an unsafe or mismatched relay destination %s', async url => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
    const construct = socketStub()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ url, ticket }) }))
    await expect(openSocket('/operator')).rejects.toThrow('Invalid socket relay response')
    expect(construct).not.toHaveBeenCalled()
  })
  it('propagates a denied ticket without opening a socket', async () => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
    const construct = socketStub()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: 'Pair your phone first.' }) }))
    await expect(openSocket('/camera/stream')).rejects.toThrow('Pair your phone first.')
    expect(construct).not.toHaveBeenCalled()
  })
})


it('never opens a socket for a cancelled attempt, even when its late ticket response resolves', async () => {
  vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
  const construct = socketStub(), controller = new AbortController()
  let finish!: (response: unknown) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise(resolve => { finish = resolve })))
  const pending = openSocket('/operator', { signal: controller.signal })
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce())
  const request = vi.mocked(fetch).mock.calls[0][1]!
  expect(request.signal?.aborted).toBe(false)
  controller.abort()
  expect(request.signal?.aborted).toBe(true)
  finish({ ok: true, status: 200, json: async () => ({ url: 'wss://relay.example/api/v2/operator', ticket }) })
  await expect(pending).rejects.toThrow()
  expect(construct).not.toHaveBeenCalled()
})

it('does not request a ticket or create a local socket when already cancelled', async () => {
  const construct = socketStub(), fetch = vi.fn(), controller = new AbortController()
  vi.stubGlobal('fetch', fetch)
  controller.abort()
  await expect(openSocket('/operator', { signal: controller.signal })).rejects.toThrow()
  expect(fetch).not.toHaveBeenCalled()
  expect(construct).not.toHaveBeenCalled()
})
