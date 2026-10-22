import { DEVICE_PEOPLE_LIMIT } from './capacity'
import type { PersonObservation } from './peopleContracts'

interface RawDetection {
  categories: { categoryName: string; score: number }[]
  boundingBox?: { originX: number; originY: number; width: number; height: number }
}

/** Keep only real person model detections. No pose counts or synthetic grid boxes enter here. */
export function personDetections(detections: readonly RawDetection[], width: number, height: number): PersonObservation[] {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return []
  const clamp = (value: number) => Math.min(1, Math.max(0, value))
  return detections.flatMap(detection => {
    const category = detection.categories.find(item => item.categoryName === 'person')
    const raw = detection.boundingBox
    if (!category || !Number.isFinite(category.score) || category.score < .25 || category.score > 1 || !raw ||
      ![raw.originX, raw.originY, raw.width, raw.height].every(Number.isFinite) || raw.width <= 0 || raw.height <= 0) return []
    const box: PersonObservation['box'] = [clamp(raw.originX / width), clamp(raw.originY / height), clamp((raw.originX + raw.width) / width), clamp((raw.originY + raw.height) / height)]
    if (box[2] <= box[0] || box[3] <= box[1]) return []
    return [{ box, score: category.score }]
  }).sort((a, b) => b.score - a.score).slice(0, DEVICE_PEOPLE_LIMIT)
}
