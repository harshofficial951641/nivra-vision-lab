import { describe, expect, it } from 'vitest'
import { AFTER_MS, BEFORE_MS, ClipBuffer } from './clipBuffer'

const frame = () => new Blob(['x'], { type: 'image/jpeg' })

describe('ClipBuffer', () => {
  it('keeps 10 s before and 8 s after the incident for that camera only', () => {
    const buffer = new ClipBuffer()
    for (let t = 0; t <= 20_000; t += 200) {
      buffer.push('a', frame(), t)
      buffer.push('b', frame(), t)
    }
    buffer.capture('e1', 'a', 20_000)
    for (let t = 20_200; t <= 30_000; t += 200) buffer.push('a', frame(), t)
    const clip = buffer.get('e1')!
    expect(clip.complete).toBe(true)
    expect(clip.frames[0].at).toBeGreaterThanOrEqual(20_000 - BEFORE_MS)
    expect(clip.frames.at(-1)!.at).toBeLessThanOrEqual(20_000 + AFTER_MS)
    expect(clip.frames.length).toBeGreaterThan(80)
  })

  it('caps the frame rate and completes on tick when the camera goes quiet', () => {
    const buffer = new ClipBuffer()
    for (let t = 0; t < 1000; t += 10) buffer.push('a', frame(), t)
    buffer.capture('e1', 'a', 1000)
    expect(buffer.get('e1')!.frames.length).toBeLessThanOrEqual(7)
    buffer.tick(1000 + AFTER_MS + 1)
    expect(buffer.get('e1')!.complete).toBe(true)
  })

  it('is idempotent per incident and releases memory', () => {
    const buffer = new ClipBuffer()
    buffer.push('a', frame(), 0)
    buffer.capture('e1', 'a', 100)
    buffer.capture('e1', 'a', 5000)
    expect(buffer.get('e1')!.peakAt).toBe(100)
    buffer.release('e1')
    expect(buffer.get('e1')).toBeNull()
  })
})
