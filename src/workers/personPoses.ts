import type { PoseLandmarks } from '../types/vision'
export type PersonRegion = [number, number, number, number]
export function expandedPersonRegion(box: PersonRegion): PersonRegion {
  const dx = (box[2] - box[0]) * .3, dy = (box[3] - box[1]) * .15
  return [Math.max(0, box[0] - dx), Math.max(0, box[1] - dy), Math.min(1, box[2] + dx), Math.min(1, box[3] + dy)]
}
export function remapPersonPose(pose: PoseLandmarks, region: PersonRegion): PoseLandmarks {
  return pose.map(point => ({ ...point, x: region[0] + point.x * (region[2] - region[0]), y: region[1] + point.y * (region[3] - region[1]), z: point.z * (region[2] - region[0]) }))
}
/** A crop must return the proposed person, rather than a nearby larger body. */
export function matchesPersonRegion(pose: PoseLandmarks, box: PersonRegion): boolean {
  const visible = (index: number) => pose[index] && (pose[index].visibility ?? 1) >= .5 && (pose[index].presence ?? 1) >= .5
  const head = [0, 1, 2, 3, 4, 5, 6, 7, 8].filter(visible)
  const indices = head.length >= 3 ? head : [11, 12, 23, 24].filter(visible)
  if (indices.length < 2) return false
  const x = indices.reduce((sum, index) => sum + pose[index].x, 0) / indices.length
  const y = indices.reduce((sum, index) => sum + pose[index].y, 0) / indices.length
  const dx = (box[2] - box[0]) * .05, dy = (box[3] - box[1]) * .05
  return x >= box[0] - dx && x <= box[2] + dx && y >= box[1] - dy && y <= box[3] + dy
}
