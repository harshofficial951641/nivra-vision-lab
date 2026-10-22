import { describe, expect, it } from 'vitest'
import { personDetections } from './personDetections'
const detection = (x: number, score = .8, categoryName = 'person') => ({ categories: [{ categoryName, score }], boundingBox: { originX: x, originY: 20, width: 20, height: 40 } })
describe('Actual person boxes', () => {
  it('normalizes twenty actual model boxes without using a ten-pose limit', () => {
    const boxes = personDetections(Array.from({ length: 20 }, (_, i) => detection(i * 40)), 1000, 100)
    expect(boxes).toHaveLength(20)
    expect(boxes[0].box).toEqual([0, .2, .02, .6])
    expect(boxes[19].box).toEqual([.76, .2, .78, .6])
  })
  it('keeps at most32 highest-confidence detections and admits the tested .25 threshold', () => {
    expect(personDetections(Array.from({ length: 40 }, (_, i) => detection(i * 20, .25 + i / 100)), 1000, 100)).toHaveLength(32)
    expect(personDetections([detection(0, .25)], 100, 100)).toHaveLength(1)
    expect(personDetections([detection(0, .249)], 100, 100)).toEqual([])
  })
  it('rejects other objects and invalid/out-of-frame boxes instead of fabricating people', () => {
    expect(personDetections([detection(10, .9, 'chair'), detection(110), detection(0, NaN), { ...detection(1), boundingBox: { originX: 0, originY: 0, width: -1, height: 20 } }], 100, 100)).toEqual([])
    expect(personDetections([detection(-10)], 100, 100)[0].box).toEqual([0, .2, .1, .6])
    expect(personDetections([detection(0)], 0, 100)).toEqual([])
  })
})
