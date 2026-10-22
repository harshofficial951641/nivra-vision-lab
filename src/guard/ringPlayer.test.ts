import { describe, expect, it } from 'vitest'
import { RING_MAX, RING_REPEAT_MS, pattern, shouldRing } from './ringPlayer'

describe('ring schedule', () => {
  it('rings at once, then every 15 s, at most four times', () => {
    expect(shouldRing(1000, 0, 0, 1000)).toBe(true)
    expect(shouldRing(1000, 1, 1000, 1000 + RING_REPEAT_MS - 1)).toBe(false)
    expect(shouldRing(1000, 1, 1000, 1000 + RING_REPEAT_MS)).toBe(true)
    expect(shouldRing(1000, RING_MAX, 0, 999_999)).toBe(false)
  })

  it('vibrates in 0.8 s bursts across the 4 s ring', () => {
    const steps = pattern(4000)
    expect(steps.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0)).toBeGreaterThanOrEqual(2800)
    expect(steps.every((s) => s > 0)).toBe(true)
  })
})
