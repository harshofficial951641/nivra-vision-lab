import { describe, expect, it } from 'vitest'
import type { PoseLandmarks } from '../types/vision'
import { mergeCropPoses, ownsPortraitPose, remapCropPose, sameCropPerson } from './portraitPoses'
const pose = (x: number, y: number, visibility = .95): PoseLandmarks => Array.from({ length: 33 }, (_, index) => ({
  x: x + (index % 2 ? -.025 : .025), y: y + (index < 9 ? -.12 : index < 13 ? -.08 : index < 25 ? .1 : .25), z: .1, visibility, presence: .95,
}))
describe('portrait multiperson observations', () => {
  it('maps crop landmarks including depth into original frame coordinates', () => {
    const input = pose(.3, .4)
    const output = remapCropPose(input, { x: .35, width: .65 })
    expect(output[0].x).toBeCloseTo(.35 + input[0].x * .65)
    expect(output[0].y).toBe(input[0].y)
    expect(output[0].z).toBeCloseTo(.065)
    expect(output[0].visibility).toBe(.95)
  })
  it('keeps two distinct people while deduplicating the same observed body in overlapping crops', () => {
    const foreground = pose(.3, .4), rear = pose(.65, .55), duplicate = pose(.652, .552)
    expect(mergeCropPoses([[foreground, rear], [duplicate]], .56, 10)).toHaveLength(2)
    expect(sameCropPerson(foreground, rear, .56)).toBe(false)
  })
  it('deduplicates a matching head with a distorted partial-body proposal and prefers the fully observed body', () => {
    const real = pose(.65, .55)
    const distorted = pose(.3, .5, .2)
    for (let index = 0; index < 9; index++) distorted[index] = { ...real[index], x: real[index].x + .005 }
    for (const index of [11, 12, 23, 24]) distorted[index] = { ...distorted[index], visibility: .95 }
    const merged = mergeCropPoses([[distorted], [real]], .56, 10)
    expect(merged).toEqual([real])
  })
  it('assigns tile ownership to the observed head even when a partial torso drifts across the seam', () => {
    const foreground = pose(.35, .4), rear = pose(.55, .6)
    const malformed = rear.map(point => ({ ...point }))
    for (const index of [11, 12, 23, 24]) malformed[index].x = .3
    expect(ownsPortraitPose(foreground, 0)).toBe(true)
    expect(ownsPortraitPose(foreground, 1)).toBe(false)
    expect(ownsPortraitPose(malformed, 0)).toBe(false)
    expect(ownsPortraitPose(rear, 1)).toBe(true)
    for (let index = 0; index < 9; index++) rear[index].visibility = .1
    expect(ownsPortraitPose(rear, 1)).toBe(true)
    expect(ownsPortraitPose(pose(.3, .4, .1), 0)).toBe(false)
  })
  it('does not merge nearby noses alone and does not exceed the heavy pose budget', () => {
    const first = pose(.3, .4), second = pose(.6, .5)
    second[0] = { ...first[0] }
    expect(sameCropPerson(first, second, .56)).toBe(false)
    expect(mergeCropPoses([Array.from({ length: 20 }, (_, index) => pose(index * .1, index * .1))], .56, 10)).toHaveLength(10)
    expect(mergeCropPoses([[], []], .56, 10)).toEqual([])
  })
})
