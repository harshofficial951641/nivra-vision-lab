import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './contracts'
vi.mock('../auth/session', () => ({ sessionToken: async () => null }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
describe('API connection deadlines', () => {
  it('releases a stalled read and makes the next attempt independently', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn().mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ready: true }) })
    vi.stubGlobal('fetch', fetch)
    const stalled = api('/state')
    const assertion = expect(stalled).rejects.toThrow('Connection is taking too long')
    await vi.advanceTimersByTimeAsync(12000)
    await assertion
    await expect(api('/state')).resolves.toEqual({ ready: true })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('allows a component to cancel its own read without mislabeling it as a timeout', async () => {
    const fetch = vi.fn().mockImplementation((_url, options) => new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
    vi.stubGlobal('fetch', fetch)
    const controller = new AbortController()
    const request = api('/state', 'GET', undefined, { signal: controller.signal })
    const assertion = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    await Promise.resolve()
    controller.abort()
    await assertion
  })
})
