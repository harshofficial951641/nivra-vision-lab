import { describe, expect, it } from 'vitest'
import { DeviceReportQueue } from './deviceReportQueue'
const event = (id: string, at = 0) => ({ id, occurredAtMs: at, detail: 'Review motion' })
describe('bounded device report delivery', () => {
  it('preserves distinct incidents when fast inference frames are coalesced', () => {
    const queue = new DeviceReportQueue(100)
    queue.push({ timestampMs: 1, events: [event('a'), event('b')] })
    queue.push({ timestampMs: 2, events: [event('c'), event('d')] })
    expect(queue.take(0)?.events.map(e => e.id)).toEqual(['a', 'b'])
    queue.push({ timestampMs: 3, events: [event('a'), event('d')] })
    expect(queue.take(50)).toBeNull()
    expect(queue.take(100)?.events.map(e => e.id)).toEqual(['c', 'd'])
    expect(queue.take(200)).toBeNull()
  })
  it('bounds combined fast and crowd traffic below the backend rate limit', () => {
    const fast = new DeviceReportQueue(100), crowd = new DeviceReportQueue(200)
    let sent = 0
    for (let at = 0; at < 1000; at += 50) {
      for (const queue of [fast, crowd]) {
        queue.push({ timestampMs: at, events: [] })
        if (queue.take(at)) sent++
      }
    }
    expect(sent).toBe(15)
  })
  it('expires stale incidents and rejects repeated source frames', () => {
    const queue = new DeviceReportQueue(100)
    queue.push({ timestampMs: 1, events: [event('old')] })
    queue.push({ timestampMs: 6000, events: [] })
    expect(queue.take(0)?.events).toEqual([])
    queue.push({ timestampMs: 6000, events: [event('repeated', 6000)] })
    expect(queue.take(100)).toBeNull()
  })
})
