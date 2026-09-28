import { describe, expect, it } from 'vitest'
import { FrameWindow } from './frameWindow'

describe('bounded camera transport', () => {
  it('sustains 12 fps with 400 ms acknowledgements instead of one frame per RTT', () => {
    const flow = new FrameWindow()
    const arrivals: { timestamp: number; due: number }[] = []
    let sent = 0
    for (let now = 0; now < 10000; now += 84) {
      while (arrivals[0]?.due <= now) flow.acknowledge(arrivals.shift()!.timestamp)
      if (flow.canSend(now, 0, 60000)) {
        flow.sent(now, now, 60000)
        arrivals.push({ timestamp: now, due: now + 400 })
        sent++
      }
      expect(arrivals.length).toBeLessThanOrEqual(8)
    }
    expect(sent).toBe(120)
  })

  it('bounds packets, bytes, socket backlog and stale outstanding work', () => {
    const flow = new FrameWindow()
    expect(flow.canSend(0, 256 * 1024)).toBe(true)
    expect(flow.canSend(0, 256 * 1024, 1)).toBe(false)
    for (let n = 0; n < 8; n++) flow.sent(n, n, 90000)
    expect(flow.canSend(10, 0)).toBe(false)
    expect(flow.acknowledge(0)).toBe(true)
    expect(flow.canSend(10, 0, 160000)).toBe(false)
    expect(flow.canSend(10, 0, 60000)).toBe(true)
    expect(flow.canSend(751, 0)).toBe(false)
    expect(flow.timedOut(10002)).toBe(true)
  })

  it('ignores duplicate/old acknowledgements and starts clean on reconnect', () => {
    const flow = new FrameWindow()
    flow.sent(10, 10, 100000)
    expect(flow.acknowledge(999)).toBe(false)
    expect(flow.acknowledge(10)).toBe(true)
    expect(flow.acknowledge(10)).toBe(false)
    expect(flow.canSend(20000, 0)).toBe(true)
    flow.sent(11, 11, 100000)
    expect(new FrameWindow().canSend(20000, 0)).toBe(true)
  })

  it('allows one unusually large valid frame without building a large-frame queue', () => {
    const flow = new FrameWindow()
    expect(flow.canSend(0, 0, 1000000)).toBe(true)
    flow.sent(0, 0, 1000000)
    expect(flow.canSend(1, 0, 1000000)).toBe(false)
    expect(flow.canSend(1, 0)).toBe(false)
    flow.acknowledge(0)
    expect(flow.canSend(2, 0, 1500001)).toBe(false)
  })
})
