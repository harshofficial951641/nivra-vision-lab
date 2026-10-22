import type { PoseLandmark, PoseLandmarks } from '../types/vision'

export interface PoseRegion { x: number; width: number }
export const PORTRAIT_POSE_REGIONS: readonly PoseRegion[] = [{ x: 0, width: .65 }, { x: .35, width: .65 }]

/** Crop coordinates return to the same full source image used by tracking and preview. */
export function remapCropPose(pose: PoseLandmarks, region: PoseRegion): PoseLandmarks {
  return pose.map(point => ({ ...point, x: region.x + point.x * region.width, z: point.z * region.width }))
}
const visible = (point: PoseLandmark | undefined): point is PoseLandmark => !!point &&
  Number.isFinite(point.x) && Number.isFinite(point.y) && (point.visibility ?? 1) >= .5 && (point.presence ?? 1) >= .5
const torsoIndices = [11, 12, 23, 24]
const quality = (pose: PoseLandmarks) => pose.reduce((score, point) => score + (visible(point) ? (point.visibility ?? 1) * (point.presence ?? 1) : 0), 0)
function torsoScale(pose: PoseLandmarks, aspect: number) {
  const points = torsoIndices.map(index => pose[index]).filter(visible)
  if (points.length < 2) return .1
  const xs = points.map(point => point.x * aspect), ys = points.map(point => point.y)
  return Math.max(.05, Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)))
}

/** Each overlapping tile owns one half of the frame, anchored to observed head joints.
 * Head ownership rejects cross-tile partial bodies whose torsos drift toward another person.
 */
export function ownsPortraitPose(pose: PoseLandmarks, tile: number): boolean {
  const head = pose.slice(0, 9).filter(visible)
  const anchor = head.length >= 3 ? head : torsoIndices.map(index => pose[index]).filter(visible)
  if (anchor.length < 2) return false
  const xs = anchor.map(point => point.x).sort((a, b) => a - b)
  const middle = Math.floor(xs.length / 2)
  const x = xs.length % 2 ? xs[middle] : (xs[middle - 1] + xs[middle]) / 2
  return tile === 0 ? x < .5 : x >= .5
}

/** Deduplicate closely matching observed head or torso joints across overlapping crops. */
export function sameCropPerson(a: PoseLandmarks, b: PoseLandmarks, aspect: number) {
  // Cropping can keep the same visible head while hallucinating a shifted torso.
  // Require a cluster of matching observed head joints, not one nearby nose.
  const head = [0, 1, 2, 3, 4, 5, 6, 7, 8].filter(index => visible(a[index]) && visible(b[index]))
  if (head.length >= 5) {
    const distances = head.map(index => Math.hypot((a[index].x - b[index].x) * aspect, a[index].y - b[index].y))
    if (distances.reduce((sum, value) => sum + value, 0) / distances.length < .018 && Math.max(...distances) < .035) return true
  }
  const indices = torsoIndices.filter(index => visible(a[index]) && visible(b[index]))
  if (indices.length < 2) return false
  const distances = indices.map(index => Math.hypot((a[index].x - b[index].x) * aspect, a[index].y - b[index].y))
  const threshold = Math.max(.015, Math.min(torsoScale(a, aspect), torsoScale(b, aspect)) * .18)
  return distances.reduce((sum, value) => sum + value, 0) / distances.length < threshold && Math.max(...distances) < threshold * 1.7
}
export function mergeCropPoses(groups: PoseLandmarks[][], aspect: number, limit: number): PoseLandmarks[] {
  const result: PoseLandmarks[] = []
  for (const pose of groups.flat()) {
    const duplicate = result.findIndex(other => sameCropPerson(pose, other, aspect))
    if (duplicate < 0) result.push(pose)
    else if (quality(pose) > quality(result[duplicate])) result[duplicate] = pose
  }
  return result.slice(0, limit)
}
