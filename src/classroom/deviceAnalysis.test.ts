import { describe, expect, it } from 'vitest'
import { demoFrame } from '../lib/demoScene'
import { DeviceAnalysis } from './deviceAnalysis'

describe('original Nivra detector on camera devices', () => {
  it('admits ten small visible bodies without merging their neighboring tracks', () => {
    const engine = new DeviceAnalysis()
    const original = demoFrame(0, 'calm').poses[0]
    const poses = Array.from({ length: 10 }, (_, i) => original.map(p => ({
      ...p, x: .075 + (i % 5) * .2 + (p.x - .34) * .22, y: .15 + Math.floor(i / 5) * .42 + p.y * .22,
    })))
    let ids: number[] = []
    for (let t = 0; t < 2000; t += 100) {
      const report = engine.update(t, 50, poses, 16 / 9, 'CPU')
      expect(report.usablePeople).toBe(10)
      expect(report.tracks).toHaveLength(10)
      expect(report.events).toEqual([])
      if (t === 0) ids = report.tracks.map(track => track.id)
      else expect(report.tracks.map(track => track.id)).toEqual(ids)
    }
  })

  it('maps focused-area observations back onto the full camera image', () => {
    const poses = demoFrame(0, 'calm').poses
    const full = new DeviceAnalysis().update(0, 10, poses, 8 / 9, 'GPU')
    const focused = new DeviceAnalysis().update(0, 10, poses, 8 / 9, 'GPU', 'right')
    focused.tracks.forEach((track, i) => {
      expect(track.box[0]).toBeCloseTo(.5 + full.tracks[i].box[0] * .5)
      expect(track.box[2]).toBeCloseTo(.5 + full.tracks[i].box[2] * .5)
      expect(track.box[1]).toBeCloseTo(full.tracks[i].box[1])
    })
  })
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
