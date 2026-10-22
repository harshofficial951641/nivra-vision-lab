import { describe, expect, it } from 'vitest'
import { mergePersonBoxes, PersonTracker, type PersonBox } from './personTracking'

const crowd = (count: number, shift = 0) => Array.from({ length: count }, (_, i) => ({
  box: [(i % 8) / 8 + shift, Math.floor(i / 8) / 4, (i % 8) / 8 + .09 + shift, Math.floor(i / 8) / 4 + .2] as PersonBox,
}))

describe('observed person boxes', () => {
  it.each([20, 32])('tracks %i people across reordered observations without creating motion evidence', count => {
    const tracker = new PersonTracker()
    const first = tracker.update(100, mergePersonBoxes(crowd(count), []))
    const second = tracker.update(2100, mergePersonBoxes(crowd(count, .005).reverse(), []))
    expect(second).toHaveLength(count)
    expect(second.map(t => t.id)).toEqual(first.map(t => t.id).reverse())
    expect(new Set(second.map(t => t.id)).size).toBe(count)
  })

  it('merges a smaller visible pose into its full-body detection once', () => {
    const detected = [{ box: [.1, .1, .3, .8] as PersonBox }, { box: [.5, .1, .7, .8] as PersonBox }]
    const poses = [{ box: [.13, .2, .27, .5] as PersonBox }, { box: [.8, .2, .9, .6] as PersonBox }]
    expect(mergePersonBoxes(detected, poses)).toEqual([detected[0].box, detected[1].box, poses[1].box])
  })

  it('bounds and validates detections, removes duplicate detector boxes', () => {
    const observations = crowd(32)
    expect(mergePersonBoxes([observations[0], ...observations, { box: [-.1, 0, .1, .2] }], [])).toHaveLength(32)
    expect(mergePersonBoxes([{ box: [NaN, 0, .1, .2] }, { box: [.2, .2, .1, .4] }], [])).toEqual([])
  })

  it('does not emit hidden tracks or restore old identities after a stall', () => {
    const tracker = new PersonTracker()
    const first = tracker.update(0, crowd(2).map(p => p.box))
    expect(tracker.update(100, [])).toEqual([])
    const next = tracker.update(3000, crowd(2).map(p => p.box))
    expect(next.map(t => t.id)).not.toEqual(first.map(t => t.id))
  })
  it('starts new anonymous tracks after the six-second observation window', () => {
    const tracker = new PersonTracker()
    const first = tracker.update(0, crowd(2).map(p => p.box))
    const next = tracker.update(6001, crowd(2).map(p => p.box))
    expect(next.map(t => t.id)).not.toEqual(first.map(t => t.id))
  })
})
