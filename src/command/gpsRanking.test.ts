import { describe, expect, it } from 'vitest'
import { gpsStatus, rankGPSGuards, recentGPS, liveGuards } from './model'
import type { WallGuard } from './types'

const now = 1_000_000
const point = { latitude: 28.6, longitude: 77.2, accuracy: 8, capturedAt: now }
const guard = (id: string, latitude: number, patch: Partial<WallGuard> = {}): WallGuard => ({
  id, name: id, status: 'available', floorId: null, x: null, y: null, online: true, push: true,
  gps: { ...point, latitude }, ...patch,
})

describe('GPS guard comparison', () => {
  it('orders available guards by current straight-line distance, keeping stale and off-shift guards behind', () => {
    const guards = [guard('far', 28.61), guard('stale', 28.6, { gps: { ...point, capturedAt: now - 120_000 } }), guard('near', 28.6001), guard('off', 28.6, { status: 'off' })]
    const ranked = rankGPSGuards(guards, point, now)
    expect(ranked.map(row => row.guard.id)).toEqual(['near', 'far', 'stale', 'off'])
    expect(ranked[0].meters).toBeGreaterThan(10)
    expect(ranked[0].meters).toBeLessThan(12)
    expect(ranked[2].meters).toBeNull()
  })
  it('does not invent distances when the incident has no saved GPS', () => {
    expect(rankGPSGuards([guard('one', 28.6)], null, now)[0].meters).toBeNull()
  })
  it('rejects future and invalid device coordinates and labels old positions', () => {
    expect(recentGPS({ ...point, capturedAt: now + 10_000 }, now)).toBe(false)
    expect(recentGPS({ ...point, latitude: 91 }, now)).toBe(false)
    expect(recentGPS({ ...point, capturedAt: now - 119_999 }, now)).toBe(true)
    expect(gpsStatus({ ...point, capturedAt: now - 120_000 }, now)).toContain('Last GPS')
    expect(gpsStatus(null, now)).toBe('GPS unavailable')
  })
  it('keeps reported indoor floor separate from device GPS', () => {
    const result = liveGuards([{ id: 'g', callsign: 'G1', name: 'Asha', userId: null, email: null, floorId: null, floorName: 'Floor 2', gps: point, post: null, shift: 'on_shift', presence: { online: true, lastSeen: now }, push: true }], new Map())
    expect(result[0].floorName).toBe('Floor 2')
    expect(result[0].gps).toEqual(point)
  })
})
