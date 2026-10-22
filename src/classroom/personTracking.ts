import { DEVICE_PEOPLE_LIMIT } from './capacity'

export type PersonBox = [number, number, number, number]
export type PersonObservation = { box: PersonBox }

const area = (b: PersonBox) => (b[2] - b[0]) * (b[3] - b[1])
function overlap(a: PersonBox, b: PersonBox) {
  const intersection = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) *
    Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]))
  return { iou: intersection / (area(a) + area(b) - intersection), contained: intersection / Math.min(area(a), area(b)) }
}
function valid(box: PersonBox) {
  return box.length === 4 && box.every(v => Number.isFinite(v) && v >= 0 && v <= 1) && box[2] > box[0] && box[3] > box[1]
}

/** Full-frame detections plus unmatched visible poses, with no inferred skeletons. */
export function mergePersonBoxes(detected: readonly PersonObservation[], poses: readonly PersonObservation[]): PersonBox[] {
  const boxes: PersonBox[] = []
  for (const { box } of detected) {
    if (valid(box) && !boxes.some(other => overlap(box, other).iou >= .65)) boxes.push([...box])
    if (boxes.length === DEVICE_PEOPLE_LIMIT) break
  }
  const matched = new Set<number>()
  for (const { box } of poses) {
    if (!valid(box)) continue
    let best = -1, score = 0
    boxes.forEach((other, index) => {
      const match = overlap(box, other)
      if (!matched.has(index) && (match.iou >= .2 || match.contained >= .65) && match.iou > score) {
        best = index; score = match.iou
      }
    })
    if (best >= 0) matched.add(best)
    else if (boxes.length < DEVICE_PEOPLE_LIMIT) { matched.add(boxes.length); boxes.push([...box]) }
  }
  return boxes
}

/** Anonymous short-lived associations. Hidden people are never emitted as observations. */
export class PersonTracker {
  private previous: { id: number; box: PersonBox }[] = []
  private timestamp = -Infinity
  private nextId = 1

  update(timestamp: number, boxes: readonly PersonBox[]) {
    const candidates: { old: number; current: number; score: number }[] = []
    if (timestamp > this.timestamp && timestamp - this.timestamp <= 6000) {
      boxes.forEach((box, current) => this.previous.forEach((track, old) => {
        const score = overlap(box, track.box).iou
        if (score >= .2) candidates.push({ old, current, score })
      }))
    }
    candidates.sort((a, b) => b.score - a.score)
    const assigned = new Map<number, number>(), used = new Set<number>()
    for (const match of candidates) {
      if (assigned.has(match.current) || used.has(match.old)) continue
      assigned.set(match.current, this.previous[match.old].id); used.add(match.old)
    }
    this.previous = boxes.slice(0, DEVICE_PEOPLE_LIMIT).map((box, index) => ({ id: assigned.get(index) ?? this.nextId++, box: [...box] as PersonBox }))
    this.timestamp = timestamp
    return this.previous.map(track => ({ ...track, box: [...track.box] as PersonBox }))
  }
}
