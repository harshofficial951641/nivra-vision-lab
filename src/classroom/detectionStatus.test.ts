import { describe, expect, it } from 'vitest'
import type { DeviceMotion, DeviceResult, DeviceStatus } from './deviceAnalysis'
import { detectionStatus } from './detectionStatus'
const ready: DeviceStatus = { state: 'ready', delegate: 'CPU', detail: '' }
const error: DeviceStatus = { state: 'error', delegate: null, detail: 'failed' }
const result = (patch: Partial<DeviceResult> = {}): DeviceResult => ({ type: 'device-result', model: 'nivra-browser-motion-v1', delegate: 'CPU', timestampMs: 1000, inferenceMs: 100, observedPeople: 2, usablePeople: 2, tracks: [], poses: [], conflict: { status: 'clear', explanation: '' }, events: [], ...patch })
const motion = (patch: Partial<DeviceMotion> = {}): DeviceMotion => ({ ...result(), type: 'device-motion', ...patch })
const live = { phase: 'live' as const, now: 1500, crowdStatus: ready, motionStatus: ready }
describe('unified camera detection status', () => {
  it.each(['idle', 'starting', 'stopped', 'reconnecting'] as const)('does not carry a prior alert into phase %s', phase => {
    const state = detectionStatus({ ...live, phase, crowd: result({ conflict: { status: 'alert', explanation: '' } }) })
    expect(state.state).toBe(phase === 'starting' || phase === 'reconnecting' ? 'starting' : 'unavailable')
    expect(state.people).toBe(0)
  })
  it('accepts a minimal wall observation without device transport fields', () => {
    expect(detectionStatus({ ...live, crowd: { timestampMs: 1000, inferenceMs: 100, observedPeople: 2, usablePeople: 2, conflict: { status: 'clear', explanation: '' } } }).state).toBe('monitoring')
  })
  it('uses a healthy two-person crowd fallback when fast motion sees only one person', () => {
    expect(detectionStatus({ ...live, crowd: result(), motion: motion({ observedPeople: 1, usablePeople: 1, conflict: { status: 'limited', explanation: '' } }) })).toMatchObject({ state: 'monitoring', people: 2, checkedPeople: 2, partialCoverage: false })
  })
  it('does not add the counts of people shared by both lanes', () => {
    expect(detectionStatus({ ...live, crowd: result({ observedPeople: 4, usablePeople: 4 }), motion: motion({ observedPeople: 4, usablePeople: 4 }) }).people).toBe(4)
  })
  it('uses the widest healthy coverage without adding shared people', () => {
    expect(detectionStatus({ ...live, crowd: result({ observedPeople: 8, usablePeople: 8 }), motion: motion({ observedPeople: 4, usablePeople: 4 }) })).toMatchObject({ state: 'monitoring', people: 8, checkedPeople: 8 })
  })
  it('makes partial fast coverage explicit when crowd motion is slow', () => {
    expect(detectionStatus({ ...live, crowd: result({ observedPeople: 20, usablePeople: 20, inferenceMs: 2400, conflict: { status: 'limited', explanation: 'Sampling slow' } }), motion: motion({ observedPeople: 4, usablePeople: 4 }) })).toMatchObject({ state: 'limited', people: 20, checkedPeople: 4, action: 'Motion checked for 4 of 20 people', partialCoverage: true })
  })
  it.each(['crowd', 'motion'] as const)('prioritizes a fresh %s alert over the other lane', lane => {
    const input = { ...live, crowd: result(), motion: motion(), crowdStatus: ready, motionStatus: ready }
    input[lane].conflict = { status: 'alert', explanation: 'Directed motion' }
    expect(detectionStatus(input).state).toBe('review')
  })
  it('expires alerts using bounded total source age independently for each lane', () => {
    const alert = { status: 'alert' as const, explanation: '' }
    expect(detectionStatus({ ...live, now: 4000, motion: motion({ conflict: alert }) }).state).toBe('review')
    expect(detectionStatus({ ...live, now: 4001, motion: motion({ conflict: alert }) }).state).toBe('unavailable')
    expect(detectionStatus({ ...live, now: 7000, crowd: result({ conflict: alert }) }).state).toBe('review')
    expect(detectionStatus({ ...live, now: 7001, crowd: result({ conflict: alert }) }).state).toBe('unavailable')
  })
  it('ignores a stale fast alert while current crowd motion can monitor', () => {
    expect(detectionStatus({ ...live, now: 5000, crowd: result({ timestampMs: 4800 }), motion: motion({ conflict: { status: 'alert', explanation: '' } }) }).state).toBe('monitoring')
  })
  it('never uses a single-person or limited legacy result as healthy motion fallback', () => {
    expect(detectionStatus({ ...live, crowd: result({ usablePeople: 1 }) }).state).toBe('limited')
    expect(detectionStatus({ ...live, crowd: result({ conflict: { status: 'limited', explanation: '' } }) }).state).toBe('limited')
  })
  it('distinguishes model loading, failures, and a fresh empty scene', () => {
    expect(detectionStatus({ ...live, crowdStatus: { ...ready, state: 'loading' } }).state).toBe('starting')
    expect(detectionStatus({ ...live, crowdStatus: error, motionStatus: error }).state).toBe('unavailable')
    expect(detectionStatus({ ...live, crowdStatus: error, motionStatus: error, crowd: result() }).state).toBe('unavailable')
    expect(detectionStatus({ ...live, crowd: result({ observedPeople: 0, usablePeople: 0, conflict: { status: 'limited', explanation: '' } }) })).toMatchObject({ state: 'monitoring', people: 0 })
  })
  it('does not trust errored lanes, stale alerts with long inference, or warming-only motion', () => {
    expect(detectionStatus({ ...live, crowd: result(), motionStatus: error, motion: motion({ conflict: { status: 'alert', explanation: '' } }) }).state).toBe('monitoring')
    expect(detectionStatus({ ...live, now: 31000, motion: motion({ inferenceMs: 30000, conflict: { status: 'alert', explanation: '' } }) }).state).toBe('unavailable')
    expect(detectionStatus({ ...live, crowd: result({ conflict: { status: 'warming', explanation: '' } }), motion: motion({ conflict: { status: 'warming', explanation: '' } }) }).state).toBe('starting')
    expect(detectionStatus({ ...live, crowdStatus: error, motionStatus: error }).action).toBe('Retry detection')
  })
  it('rejects future-source and invalid duration reports', () => {
    expect(detectionStatus({ ...live, now: 500, crowd: result({ conflict: { status: 'alert', explanation: '' } }) }).state).toBe('unavailable')
    expect(detectionStatus({ ...live, crowd: result({ inferenceMs: NaN, conflict: { status: 'alert', explanation: '' } }) }).state).toBe('unavailable')
  })
})
