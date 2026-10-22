import { describe, expect, it } from 'vitest'
import { analysisRegion, DeviceBudget } from './deviceBudget'

describe('device workload budget', () => {
  it('reduces preview work for slow inference, recovers, and ignores invalid timings', () => {
    const budget = new DeviceBudget()
    expect(budget.previewSide).toBe(960)
    budget.observe(500)
    expect(budget.previewSide).toBe(640)
    expect(budget.analysisInterval).toBe(500)
    budget.observe(NaN)
    budget.observe(-1)
    expect(budget.inferenceMs).toBe(500)
    for (let i = 0; i < 25; i++) budget.observe(20)
    expect(budget.previewSide).toBe(960)
    expect(budget.analysisInterval).toBe(50)
  })
  it('keeps every focus region within the source image', () => {
    for (const area of ['full', 'left', 'center', 'right'] as const) {
      const region = analysisRegion(area)
      expect(region.x).toBeGreaterThanOrEqual(0)
      expect(region.x + region.width).toBeLessThanOrEqual(1)
    }
  })
})
