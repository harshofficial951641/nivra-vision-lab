import { getContainTransform } from '../lib/geometry'
import { POSE_CONNECTIONS } from '../lib/drawVision'
import { DEVICE_PEOPLE_LIMIT } from './capacity'

/** Actual observed joints only. null means absent, invalid, or outside the image. */
export type SkeletonJoint = [number, number, number] | null
export type CameraPose = SkeletonJoint[]

export function skeletonGeometry(poses: CameraPose[] | undefined, sourceWidth: number, sourceHeight: number, width: number, height: number) {
  if (![sourceWidth, sourceHeight, width, height].every(value => Number.isFinite(value) && value > 0)) return []
  const fit = getContainTransform({ width: sourceWidth, height: sourceHeight }, { width, height })
  return (poses ?? []).slice(0, DEVICE_PEOPLE_LIMIT).flatMap((pose, index) => {
    if (!Array.isArray(pose) || pose.length !== 33) return []
    const points = pose.map((point, joint) => {
      if (!Array.isArray(point) || point.length !== 3 || !point.every(Number.isFinite) || point[0] < 0 || point[0] > 1 || point[1] < 0 || point[1] > 1 || point[2] < .55 || point[2] > 1) return null
      return { joint, x: fit.offsetX + point[0] * fit.renderedWidth, y: fit.offsetY + point[1] * fit.renderedHeight, confidence: point[2] }
    })
    const lines = POSE_CONNECTIONS.flatMap(([from, to]) => {
      const start = points[from], end = points[to]
      if (!start || !end) return []
      const length = Math.hypot((pose[from]![0] - pose[to]![0]) * sourceWidth, (pose[from]![1] - pose[to]![1]) * sourceHeight)
      if (Math.min(start.confidence, end.confidence) < .75 && length > Math.hypot(sourceWidth, sourceHeight) * .5) return []
      return [{ from, to, start, end }]
    })
    return [{ index, points: points.filter(point => point !== null), lines }]
  })
}
