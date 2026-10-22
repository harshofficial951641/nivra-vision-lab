import { describe, expect, it } from 'vitest'
import type { Incident } from '../classroom/contracts'
import {
  ReviewError,
  alertLevel,
  applyGuardAction,
  applyReview,
  median,
  orderCameras,
  responseSteps,
  sampleCameras,
  stageOf,
  wallStats,
} from './model'
import { SAMPLE_GUARDS, conePath, incidentPoint, nearestGuards, CAMERA_SLOTS } from './siteMap'

const now = Date.UTC(2026, 9, 21, 12)
const event = (patch: Partial<Incident> = {}): Incident => ({
  id: 'e1',
  camera_id: 'cam-04',
  camera_name: 'Atrium East',
  location: 'Orbit Mall · Floor 2',
  received_at: now - 5000,
  source_ms: 0,
  evidence_ms: 0,
  model: 'sample',
  detail: 'Signal',
  status: 'open',
  revision: 0,
  updated_at: now - 5000,
  ...patch,
})

describe('review state machine', () => {
  it('walks view → confirm with guard → guard ack → on scene → clear', () => {
    let e = applyReview(event(), 'view', {}, now)
    expect(e).toMatchObject({ status: 'acknowledged', reviewed_at: now, revision: 1 })
    expect(applyReview(e, 'view', {}, now + 5)).toBe(e)
    e = applyReview(e, 'confirm', { guard: 'G2', note: '  calm  ' }, now + 1000)
    expect(e).toMatchObject({ decision: 'confirmed', guard: 'G2', alerted_at: now + 1000, note: 'calm', revision: 2 })
    expect(stageOf(e)).toBe('alerted')
    e = applyGuardAction(e, 'ack', now + 2000)
    expect(stageOf(e)).toBe('acknowledged')
    e = applyGuardAction(e, 'on_scene', now + 3000)
    e = applyGuardAction(e, 'clear', now + 4000)
    expect(e.status).toBe('resolved')
    expect(stageOf(e)).toBe('cleared')
  })

  it('requires a reason for a false alarm and closes it', () => {
    expect(() => applyReview(event(), 'dismiss', {}, now)).toThrow(ReviewError)
    const e = applyReview(event(), 'dismiss', { reason: 'greeting' }, now)
    expect(e).toMatchObject({ decision: 'false_alarm', reason: 'greeting', status: 'resolved', reviewed_at: now })
    expect(() => applyReview(e, 'confirm', {}, now)).toThrow(ReviewError)
  })

  it('rejects alerting before confirmation and re-alert clears guard progress', () => {
    expect(() => applyReview(event(), 'alert', { guard: 'G2' }, now)).toThrow(ReviewError)
    let e = applyReview(event(), 'confirm', { guard: 'G2' }, now)
    e = applyGuardAction(e, 'decline', now + 1)
    expect(stageOf(e)).toBe('declined')
    e = applyReview(e, 'alert', { guard: 'G4' }, now + 2)
    expect(e).toMatchObject({ guard: 'G4', guard_declined_at: null, guard_ack_at: null })
  })

  it('does not let a guard act twice', () => {
    const e = applyGuardAction(applyReview(event(), 'confirm', { guard: 'G2' }, now), 'ack', now)
    expect(() => applyGuardAction(e, 'ack', now)).toThrow(ReviewError)
    expect(() => applyGuardAction(e, 'clear', now)).toThrow(ReviewError)
  })
})

describe('wall model', () => {
  it('flags a camera until the decision, then holds a confirmed state', () => {
    expect(alertLevel('cam-04', [event()])).toBe('review')
    const confirmed = applyReview(event(), 'confirm', {}, now)
    expect(alertLevel('cam-04', [confirmed])).toBe('confirmed')
    expect(alertLevel('cam-04', [applyReview(event(), 'dismiss', { reason: 'other' }, now)])).toBeNull()
  })

  it('orders flagged, then pinned, then nearest cameras and sinks offline ones', () => {
    const order = orderCameras(sampleCameras(), [event()], ['cam-01'], now).map((c) => c.id)
    expect(order[0]).toBe('cam-04')
    expect(order[1]).toBe('cam-01')
    expect(order.at(-1)).toBe('cam-09')
  })

  it('tells the false-alarm story without guard steps', () => {
    const steps = responseSteps(applyReview(event(), 'dismiss', { reason: 'play_sport' }, now), 'CAM-04')
    expect(steps.map((s) => s.key)).toEqual(['detected', 'viewed', 'decision'])
    expect(steps[2].label).toContain('Play / sport')
  })

  it('marks the first missing step as current', () => {
    const steps = responseSteps(applyReview(event(), 'view', {}, now), 'CAM-04')
    expect(steps.find((s) => s.tone === 'current')?.key).toBe('decision')
  })

  it('computes today stats from records', () => {
    const viewed = applyReview(event(), 'view', {}, now)
    const stats = wallStats(sampleCameras(), [viewed], now)
    expect(stats).toMatchObject({ live: 9, total: 10, offline: 1, reviews: 1, open: 1, reviewSeconds: 5 })
    expect(median([3, 1, 2, 10])).toBe(2.5)
    expect(median([])).toBeNull()
  })
})

describe('site map', () => {
  it('ranks available guards before guards on break', () => {
    const ranked = nearestGuards(incidentPoint(CAMERA_SLOTS[3]), SAMPLE_GUARDS)
    expect(ranked[0].guard.status).toBe('available')
    expect(ranked.at(-1)?.guard.status).toBe('break')
    expect(ranked[0].meters).toBeGreaterThan(0)
  })

  it('draws a closed wedge for a camera', () => {
    expect(conePath({ x: 0, y: 0, angle: 0, fov: 90, range: 10 })).toMatch(/^M 0 0 L 7\.1 -7\.1 A 10 10 0 0 1 7\.1 7\.1 Z$/)
  })
})

describe('helpers', () => {
  it('keeps a zoomed route window inside the plan and around both points', async () => {
    const { routeView } = await import('./siteMap')
    const view = routeView({ x: 690, y: 452 }, { x: 701, y: 316 })
    expect(view.x).toBeGreaterThanOrEqual(0)
    expect(view.x + view.w).toBeLessThanOrEqual(1000)
    expect(view.y + view.h).toBeLessThanOrEqual(620)
    expect(view.x).toBeLessThan(690)
    expect(view.y).toBeLessThan(316)
  })
})
