import type { DeviceResult, DeviceStatus } from './deviceAnalysis'

export type DetectionObservation = Pick<DeviceResult, 'timestampMs' | 'inferenceMs' | 'observedPeople' | 'usablePeople' | 'conflict'>

export type DetectionPhase = 'idle' | 'starting' | 'live' | 'stopped' | 'reconnecting'
export interface DetectionStatusInput {
  phase: DetectionPhase
  /** Use the same monotonic clock as the reports' camera-source timestampMs. */
  now: number
  crowd?: DetectionObservation | null
  crowdStatus?: DeviceStatus | null
  motion?: DetectionObservation | null
  motionStatus?: DeviceStatus | null
}
export interface DetectionStatusSummary {
  state: 'starting' | 'monitoring' | 'review' | 'limited' | 'unavailable'
  label: string
  action: string
  people: number
  checkedPeople: number
  partialCoverage: boolean
}
const count = (value: number) => Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0
function fresh<T extends DetectionObservation>(report: T | null | undefined, now: number, ageLimit: number): T | null {
  if (!report || !Number.isFinite(now) || !Number.isFinite(report.timestampMs) || !Number.isFinite(report.inferenceMs) || report.inferenceMs < 0) return null
  const age = now - report.timestampMs
  // Total source age includes model computation; slow work cannot extend freshness.
  return age >= 0 && age <= ageLimit ? report : null
}
const usable = (report: DetectionObservation | null, status?: DeviceStatus | null) =>
  !!report && status?.state !== 'error' && report.conflict.status !== 'limited' && report.conflict.status !== 'warming' && count(report.usablePeople) >= 2

/** One camera status, without merging identities or replaying stale alerts. */
export function detectionStatus(input: DetectionStatusInput): DetectionStatusSummary {
  const empty = { people: 0, checkedPeople: 0, partialCoverage: false }
  const summary = (state: DetectionStatusSummary['state'], label: string, action: string, coverage = empty): DetectionStatusSummary => ({ state, label, action, ...coverage })
  if (input.phase === 'idle') return summary('unavailable', 'Detection off', 'Start camera to monitor.')
  if (input.phase === 'stopped') return summary('unavailable', 'Detection stopped', 'Reconnect camera to resume monitoring.')
  if (input.phase === 'reconnecting') return summary('starting', 'Reconnecting camera', 'Keep this page open.')
  if (input.phase === 'starting') return summary('starting', 'Starting detection', 'Keep this page open.')

  const crowd = input.crowdStatus?.state === 'error' ? null : fresh(input.crowd, input.now, 6000)
  const motion = input.motionStatus?.state === 'error' ? null : fresh(input.motion, input.now, 3000)
  const people = Math.max(count(crowd?.observedPeople ?? 0), count(motion?.observedPeople ?? 0), count(crowd?.usablePeople ?? 0), count(motion?.usablePeople ?? 0))
  // The original motion path can miss an occluded person that the crowd pose
  // path sees. A healthy crowd result remains a valid independent fallback.
  const candidates = [usable(motion, input.motionStatus) ? motion : null, usable(crowd, input.crowdStatus) ? crowd : null]
    .filter((report): report is DetectionObservation => report !== null)
  const selected = candidates.sort((a, b) => b.usablePeople - a.usablePeople || a.inferenceMs - b.inferenceMs)[0] ?? null
  const checkedPeople = selected ? count(selected.usablePeople) : 0
  const coverage = { people, checkedPeople, partialCoverage: checkedPeople > 0 && checkedPeople < people }
  if (crowd?.conflict.status === 'alert' || motion?.conflict.status === 'alert') {
    return summary('review', 'Review interaction', 'Possible conflict. Check the live camera.', coverage)
  }
  const failed = input.crowdStatus?.state === 'error' && (!input.motionStatus || input.motionStatus.state === 'error') || input.motionStatus?.state === 'error' && !input.crowdStatus
  if (failed) return summary('unavailable', 'Detection unavailable', 'Retry detection', coverage)
  if (selected) return coverage.partialCoverage
    ? summary('limited', 'Limited motion coverage', `Motion checked for ${checkedPeople} of ${people} people`, coverage)
    : summary('monitoring', 'Monitoring', 'Keep the camera steady and this page open.', coverage)

  if (crowd || motion) {
    if (crowd?.conflict.status === 'warming' || motion?.conflict.status === 'warming') return summary('starting', 'Starting detection', 'Establishing motion from fresh camera samples.', coverage)
    if (people === 0 && (crowd && input.crowdStatus?.state !== 'error' || motion && input.motionStatus?.state !== 'error')) {
      return summary('monitoring', 'Monitoring', 'Waiting for people to enter the view.', coverage)
    }
    return summary('limited', 'Motion check limited', people < 2 ? 'Keep interacting people and their arms visible.' : 'Motion could not be checked reliably. Check the live camera.', coverage)
  }
  if (input.motionStatus?.state === 'loading' || input.crowdStatus?.state === 'loading') {
    return summary('starting', 'Starting detection', 'Keep this page open.')
  }
  if (input.crowd || input.motion) return summary('unavailable', 'Waiting for detection', 'Keep this page open for fresh detection results.')
  return summary('starting', 'Starting detection', 'Waiting for the first detection sample.')
}
