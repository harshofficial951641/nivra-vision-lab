import { gpsDistance, validGPS, type GPSLocation } from '../location/gps'
import type { CameraLocation, Incident } from '../classroom/contracts'
import { CAMERA_SLOTS, slotFromPlacement } from './siteMap'
import type { CameraSlot, GuardRecord, MapFloor, WallGuard } from './types'

export type ReviewAction = 'view' | 'confirm' | 'dismiss' | 'close' | 'alert' | 'on_scene' | 'clear'
export type GuardAction = 'ack' | 'decline' | 'on_scene' | 'clear'
export type DismissReason = NonNullable<Incident['reason']>
export interface ReviewPayload {
  reason?: DismissReason
  note?: string
  guard?: string
}

export const REASONS: { id: DismissReason; label: string }[] = [
  { id: 'play_sport', label: 'Play / sport' },
  { id: 'greeting', label: 'Greeting' },
  { id: 'camera_glitch', label: 'Camera glitch' },
  { id: 'other', label: 'Other' },
]
export const reasonLabel = (reason: Incident['reason']) =>
  REASONS.find((r) => r.id === reason)?.label ?? 'Other'

export class ReviewError extends Error {}

/**
 * Client copy of the service's review state machine
 * (service/nivra/classroom_store.py Store.review). Used by the sample
 * workspace so demo and live behave the same.
 */
export function applyReview(
  event: Incident,
  action: ReviewAction,
  payload: ReviewPayload,
  now: number,
): Incident {
  if (action === 'view' && event.status !== 'open') return event
  const decision = event.decision ?? null
  const reviewed = event.reviewed_at ?? now
  const note = payload.note?.trim() || undefined
  let next: Partial<Incident>
  if (action === 'view') next = { status: 'acknowledged', reviewed_at: now }
  else if (action === 'confirm' && event.status !== 'resolved' && !decision) {
    next = { decision: 'confirmed', status: 'acknowledged', decided_at: now, reviewed_at: reviewed }
    if (payload.guard) Object.assign(next, alertFields(payload.guard, now))
    if (note) next.note = note
  } else if (action === 'dismiss' && event.status !== 'resolved' && !decision) {
    if (!payload.reason) throw new ReviewError('Pick a reason for the false alarm.')
    next = { decision: 'false_alarm', reason: payload.reason, status: 'resolved', decided_at: now, reviewed_at: reviewed }
    if (note) next.note = note
  } else if (action === 'close' && event.status !== 'resolved' && !decision) {
    next = { status: 'resolved' }
  } else if (action === 'alert' && decision === 'confirmed' && event.status === 'acknowledged') {
    if (!payload.guard) throw new ReviewError('Choose a guard to alert.')
    next = alertFields(payload.guard, now)
  } else if (action === 'on_scene' && event.alerted_at && !event.on_scene_at && event.status === 'acknowledged')
    next = { on_scene_at: now }
  else if (action === 'clear' && decision === 'confirmed' && event.status === 'acknowledged')
    next = { status: 'resolved' }
  else throw new ReviewError('This incident has already moved on. The screen will refresh.')
  return { ...event, ...next, revision: event.revision + 1, updated_at: now }
}

const alertFields = (guard: string, now: number): Partial<Incident> => ({
  guard,
  alerted_at: now,
  guard_ack_at: null,
  guard_declined_at: null,
  on_scene_at: null,
})

/** Client copy of the guard action rules used by the sample workspace. */
export function applyGuardAction(event: Incident, action: GuardAction, now: number): Incident {
  const waiting =
    event.alerted_at && event.status === 'acknowledged' && !event.guard_ack_at && !event.guard_declined_at
  let next: Partial<Incident>
  if (action === 'ack' && waiting) next = { guard_ack_at: now }
  else if (action === 'decline' && waiting) next = { guard_declined_at: now }
  else if (action === 'on_scene' && event.guard_ack_at && !event.on_scene_at) next = { on_scene_at: now }
  else if (action === 'clear' && event.on_scene_at && event.status === 'acknowledged') next = { status: 'resolved' }
  else throw new ReviewError('This alert has already changed.')
  return { ...event, ...next, revision: event.revision + 1, updated_at: now }
}

export type Stage =
  | 'awaiting'
  | 'viewing'
  | 'confirmed'
  | 'alerted'
  | 'acknowledged'
  | 'declined'
  | 'on_scene'
  | 'cleared'
  | 'false_alarm'

export function stageOf(event: Incident): Stage {
  if (event.decision === 'false_alarm') return 'false_alarm'
  if (event.status === 'resolved') return 'cleared'
  if (event.decision === 'confirmed') {
    if (event.on_scene_at) return 'on_scene'
    if (event.guard_declined_at) return 'declined'
    if (event.guard_ack_at) return 'acknowledged'
    if (event.alerted_at) return 'alerted'
    return 'confirmed'
  }
  return event.status === 'open' ? 'awaiting' : 'viewing'
}

/** Needs a human decision: not decided and not closed. */
export const needsDecision = (event: Incident) =>
  !event.decision && event.status !== 'resolved'
/** Confirmed and still being handled. */
export const isActiveResponse = (event: Incident) =>
  event.decision === 'confirmed' && event.status !== 'resolved'

export type AlertLevel = 'review' | 'confirmed' | null
export function alertLevel(cameraId: string, events: Incident[]): AlertLevel {
  const own = events.filter((e) => e.camera_id === cameraId)
  if (own.some(needsDecision)) return 'review'
  if (own.some(isActiveResponse)) return 'confirmed'
  return null
}

export interface ClockStep {
  key: string
  label: string
  at: number | null
  tone?: 'done' | 'current' | 'pending' | 'warning'
}

/** The response story of one incident, in order, for the response clock. */
export function responseSteps(event: Incident, cameraLabel: string): ClockStep[] {
  const steps: ClockStep[] = [
    { key: 'detected', label: `Detected on ${cameraLabel}`, at: event.received_at },
    { key: 'viewed', label: 'Reviewer opened the clip', at: event.reviewed_at ?? null },
  ]
  if (event.status === 'resolved' && !event.decision) {
    steps.push({ key: 'closed', label: 'Alert closed without a decision', at: event.updated_at })
  } else if (event.decision === 'false_alarm') {
    steps.push({ key: 'decision', label: `Logged as false alarm · ${reasonLabel(event.reason)}`, at: event.decided_at ?? null })
  } else {
    steps.push(
      { key: 'decision', label: event.decision === 'confirmed' ? 'Confirmed as real incident' : 'Decision', at: event.decided_at ?? null },
      { key: 'alerted', label: event.guard ? `Guard ${event.guard} alerted` : 'Guard alerted', at: event.alerted_at ?? null },
      event.guard_declined_at
        ? { key: 'ack', label: `${event.guard} can't respond`, at: event.guard_declined_at, tone: 'warning' }
        : { key: 'ack', label: event.guard ? `${event.guard} acknowledged` : 'Guard acknowledged', at: event.guard_ack_at ?? null },
      { key: 'scene', label: 'Guard on scene', at: event.on_scene_at ?? null },
      { key: 'clear', label: 'Situation clear', at: event.decision === 'confirmed' && event.status === 'resolved' ? event.updated_at : null },
    )
  }
  const firstPending = steps.findIndex((s) => s.at == null)
  return steps.map((step, index) => ({
    ...step,
    tone: step.tone ?? (step.at != null ? 'done' : index === firstPending ? 'current' : 'pending'),
  }))
}

export interface WallCamera {
  paired?: boolean
  compute?: CameraLocation['compute']
  analysis?: CameraLocation['analysis']
  deviceStatus?: CameraLocation['deviceStatus']
  result?: CameraLocation['result']
  motionResult?: CameraLocation['motionResult']
  motionStatus?: CameraLocation['motionStatus']
  error?: string | null
  generation?: string | null
  analysisPreview?: { url: string; timestampMs?: number; received?: number; width?: number; height?: number; generation?: string; analysisFrame?: boolean }
  preview?: { timestampMs?: number; received?: number; width?: number; height?: number; generation?: string; analysisFrame?: boolean }

  building?: string
  floor?: string
  gps?: GPSLocation | null
  id: string
  /** Short label shown on tiles and the map, e.g. CAM-04. */
  label: string
  name: string
  floorId: string | null
  /** Geometry in plan units; null when the camera is not placed on a floor. */
  slot: CameraSlot | null
  status: 'live' | 'connecting' | 'offline' | 'paused'
  fps: number | null
  image: string | null
  people: number | null
  sample: boolean
}

export function liveCameras(
  cameras: CameraLocation[],
  floors: Map<string, MapFloor>,
  previews: Record<string, { url: string; timestampMs?: number; received?: number; width?: number; height?: number; generation?: string; analysisFrame?: boolean }>,
  fps: Record<string, number>,
  analysisPreviews: Record<string, { url: string; timestampMs?: number; received?: number; width?: number; height?: number; generation?: string; analysisFrame?: boolean }> = {},
): WallCamera[] {
  return cameras.map((camera, index) => {
    const placement = camera.placement ?? null
    const floor = placement ? floors.get(placement.floorId) : undefined
    const label = camera.label || `CAM-${String(index + 1).padStart(2, '0')}`
    const analyzed = analysisPreviews[camera.id]
    // A slow detector must never pace the live camera image. Its source frame
    // remains separate for an explicit review, with markings tied to that frame.
    const preview = previews[camera.id]
    const analysisPreview = analyzed?.analysisFrame && analyzed.generation === camera.generation && camera.result &&
      Number.isFinite(analyzed.timestampMs) && Math.abs(analyzed.timestampMs! - camera.result.timestampMs) <= 180 ? analyzed : undefined
    return {
      id: camera.id,
      paired: camera.paired,
      compute: camera.compute,
      analysis: camera.analysis,
      deviceStatus: camera.deviceStatus,
      result: camera.result,
      motionResult: camera.motionResult,
      motionStatus: camera.motionStatus,
      error: camera.error,
      generation: camera.generation,
      preview,
      analysisPreview,
      gps: camera.gps ?? null,
      building: camera.building,
      floor: camera.floor,
      label,
      name: camera.name,
      floorId: floor?.id ?? null,
      slot: placement && floor ? slotFromPlacement({ ...camera, label }, placement, floor) : null,
      status: camera.feed === 'live' ? 'live' : camera.feed === 'waiting' ? 'connecting' : camera.feed === 'paused' ? 'paused' : 'offline',
      fps: camera.feed === 'live' ? fps[camera.id] ?? null : null,
      image: preview?.url ?? null,
      people: camera.result?.coverage?.observedPeople ?? null,
      sample: false,
    }
  })
}

export function liveGuards(guards: GuardRecord[], floors: Map<string, MapFloor>): WallGuard[] {
  return guards.map((guard) => {
    const floor = guard.floorId ? floors.get(guard.floorId) : undefined
    return {
      id: guard.callsign,
      gps: guard.gps ?? null,
      floorName: guard.floorName ?? floor?.name ?? null,
      name: guard.name,
      floorId: guard.floorId,
      x: guard.post && floor ? guard.post.x * floor.width : null,
      y: guard.post && floor ? guard.post.y * floor.height : null,
      status: guard.shift === 'on_shift' ? 'available' : guard.shift === 'break' ? 'break' : 'off',
      online: guard.presence?.online ?? null,
      push: guard.push ?? null,
    }
  })
}

export const SAMPLE_PEOPLE: Record<string, number> = {
  'cam-07': 24, 'cam-06': 18, 'cam-02': 14, 'cam-08': 12, 'cam-04': 11,
  'cam-01': 9, 'cam-05': 5, 'cam-10': 5, 'cam-03': 3, 'cam-09': 0,
}
export const sampleCameras = (): WallCamera[] =>
  CAMERA_SLOTS.map((slot) => ({
    id: slot.id,
    label: slot.label,
    name: slot.name,
    floorId: 'sample',
    building: 'Sample mall',
    floor: 'Ground floor',
    slot,
    status: slot.id === 'cam-09' ? 'offline' : 'live',
    fps: slot.id === 'cam-09' ? null : 10,
    image: slot.image || null,
    people: SAMPLE_PEOPLE[slot.id] ?? null,
    sample: true,
  }))

/** Newest incident that is still in play, else the newest within ten minutes. */
export function focusIncident(events: Incident[], now: number) {
  const sorted = [...events].sort((a, b) => b.received_at - a.received_at)
  return (
    sorted.find((e) => needsDecision(e) || isActiveResponse(e)) ??
    sorted.find((e) => now - e.updated_at < 600_000) ??
    null
  )
}

/**
 * Wall order: flagged first, then pinned, then cameras nearest the active
 * incident, then the busiest views. Offline cameras sink unless flagged.
 */
export function orderCameras(
  cameras: WallCamera[],
  events: Incident[],
  pinned: string[],
  now: number,
) {
  const focus = focusIncident(events, now)
  const focusCamera = focus ? cameras.find((c) => c.id === focus.camera_id) : undefined
  const score = (camera: WallCamera) => {
    const level = alertLevel(camera.id, events)
    if (level === 'review') return 0
    if (level === 'confirmed') return 1
    if (pinned.includes(camera.id)) return 2
    if (camera.status === 'offline') return 9
    return 3
  }
  const nearness = (camera: WallCamera) =>
    validGPS(focusCamera?.gps) && validGPS(camera.gps)
      ? gpsDistance(focusCamera.gps, camera.gps)
      : Number.MAX_SAFE_INTEGER
  return [...cameras].sort(
    (a, b) =>
      score(a) - score(b) ||
      nearness(a) - nearness(b) ||
      (b.people ?? 0) - (a.people ?? 0) ||
      a.label.localeCompare(b.label, undefined, { numeric: true }),
  )
}

const startOfToday = (now: number) => {
  const date = new Date(now)
  date.setHours(0, 0, 0, 0)
  return date.getTime()
}

export function median(values: number[]) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

export function wallStats(cameras: WallCamera[], events: Incident[], now: number) {
  const today = events.filter((e) => e.received_at >= startOfToday(now))
  const reviewSeconds = median(
    today.flatMap((e) => (e.reviewed_at ? [(e.reviewed_at - e.received_at) / 1000] : [])),
  )
  const fps = cameras.flatMap((c) => (c.status === 'live' && c.fps != null ? [c.fps] : []))
  return {
    live: cameras.filter((c) => c.status === 'live').length,
    total: cameras.length,
    offline: cameras.filter((c) => c.status === 'offline').length,
    reviewSeconds,
    reviews: today.length,
    confirmed: today.filter((e) => e.decision === 'confirmed').length,
    falseAlarms: today.filter((e) => e.decision === 'false_alarm').length,
    open: today.filter(needsDecision).length,
    fps: fps.length ? fps.reduce((a, b) => a + b, 0) / fps.length : null,
  }
}

export const formatClock = (time: number) =>
  new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

export function formatElapsed(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(total / 60)
  return `${String(minutes).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}

export const incidentRef = (event: Incident) =>
  `R-${event.id.replace(/[^a-z0-9]/gi, '').slice(-4).toUpperCase()}`

/** Device coordinates age out quickly. Never infer an indoor floor from GPS. */
export function recentGPS(point: GPSLocation | null | undefined, now: number): point is GPSLocation {
  return validGPS(point) && point.capturedAt <= now + 5_000 && now - point.capturedAt < 120_000
}

export function gpsStatus(point: GPSLocation | null | undefined, now: number) {
  if (!validGPS(point)) return 'GPS unavailable'
  const age = Math.max(0, now - point.capturedAt)
  return `${recentGPS(point, now) ? 'GPS' : 'Last GPS'} ${formatElapsed(age)} ago · ±${Math.round(point.accuracy)} m`
}

export function cameraPlace(camera: WallCamera) {
  return [camera.building, camera.floor].filter(Boolean).join(' · ')
}

/** Straight-line comparison against the incident's saved position, never a route or ETA. */
export function rankGPSGuards(guards: WallGuard[], destination: GPSLocation | null | undefined, now: number) {
  return guards.map(guard => ({
    guard,
    meters: validGPS(destination) && recentGPS(guard.gps, now) ? gpsDistance(destination, guard.gps) : null,
  })).sort((a, b) => Number(b.guard.status === 'available') - Number(a.guard.status === 'available') ||
    (a.meters ?? Number.POSITIVE_INFINITY) - (b.meters ?? Number.POSITIVE_INFINITY) ||
    a.guard.id.localeCompare(b.guard.id, undefined, { numeric: true }))
}
