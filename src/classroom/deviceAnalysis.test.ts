import { describe, expect, it } from 'vitest'
import { demoFrame } from '../lib/demoScene'
import { DeviceAnalysis } from './deviceAnalysis'

describe('original Nivra detector on camera devices', () => {
  it('produces a single-hit review with observed regions; calm interactions stay quiet', () => {
    for (const scenario of ['conflict', 'calm'] as const) {
      const engine = new DeviceAnalysis()
      const events = new Set<string>()
      for (let t = 0; t <= 3000; t += 100) {
        const report = engine.update(t, 22, demoFrame(t, scenario).poses, 16 / 9, 'GPU')
        report.events.forEach(e => events.add(e.id))
        expect(report.model).toBe('nivra-browser-motion-v1')
        expect(report.tracks.length).toBeLessThanOrEqual(report.usablePeople)
      }
      expect(events.size).toBe(scenario === 'conflict' ? 1 : 0)
    }
  })

  it('does not invent evidence when pose visibility disappears', () => {
    const engine = new DeviceAnalysis()
    engine.update(0, 30, demoFrame(0, 'calm').poses, 16 / 9, 'CPU')
    const lost = engine.update(800, 30, [], 16 / 9, 'CPU')
    expect(lost.tracks).toEqual([])
    expect(lost.events).toEqual([])
    expect(lost.conflict.status).toBe('limited')
  })
})
