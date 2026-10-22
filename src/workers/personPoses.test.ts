import { describe, expect, it } from 'vitest'
import type { PoseLandmarks } from '../types/vision'
import { expandedPersonRegion, matchesPersonRegion, remapPersonPose } from './personPoses'
const pose = (x: number, y: number): PoseLandmarks => Array.from({ length: 33 }, () => ({ x, y, z: .1, visibility: .9, presence: .9 }))
describe('person pose crop context', () => {
  it('keeps horizontal reach space for arm motion while clamping the crop to camera pixels', () => {
    expect(expandedPersonRegion([.2, .2, .4, .8])).toEqual([.14, .11, .46, .89])
    const edge = expandedPersonRegion([.01, .01, .99, .99])
    expect(edge).toEqual([0, 0, 1, 1])
  })
  it('maps only observed crop joints back to source coordinates and rejects a neighboring head', () => {
    const region = expandedPersonRegion([.2, .2, .4, .8])
    const mapped = remapPersonPose(pose(.5, .5), region)
    expect(mapped[0].x).toBeCloseTo(.3)
    expect(mapped[0].y).toBeCloseTo(.5)
    expect(matchesPersonRegion(mapped, [.2, .2, .4, .8])).toBe(true)
    expect(matchesPersonRegion(pose(.7, .5), [.2, .2, .4, .8])).toBe(false)
  })
})
