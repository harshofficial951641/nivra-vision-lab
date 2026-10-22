import { describe, expect, it, vi, afterEach } from 'vitest'
import { captureGPS, googleMapsURL, gpsDistance, validGPS } from './gps'
const point = { latitude: 28.6139, longitude: 77.209, accuracy: 12, capturedAt: 1000 }
type PositionSuccess = (position: { coords: typeof point; timestamp: number }) => void
afterEach(() => vi.unstubAllGlobals())
describe('camera GPS', () => {
  it('uses coordinates as a Google Maps destination and lets Maps choose the guard origin', () => {
    const url = new URL(googleMapsURL(point, true))
    expect(url.hostname).toBe('www.google.com')
    expect(url.searchParams.get('api')).toBe('1')
    expect(url.searchParams.get('destination')).toBe('28.6139,77.209')
    expect(url.searchParams.get('travelmode')).toBe('walking')
    expect(url.searchParams.has('origin')).toBe(false)
    expect(new URL(googleMapsURL(point)).searchParams.get('query')).toBe('28.6139,77.209')
  })
  it('accepts the equator and rejects invalid coordinates or accuracy', () => {
    expect(validGPS({ ...point, latitude: 0, longitude: 0 })).toBe(true)
    for (const invalid of [null, { ...point, latitude: 91 }, { ...point, longitude: NaN }, { ...point, accuracy: -1 }, { ...point, capturedAt: -1 }, { ...point, capturedAt: Infinity }]) expect(validGPS(invalid)).toBe(false)
  })
  it('captures a fresh high-accuracy reading', async () => {
    vi.stubGlobal('isSecureContext', true)
    const getCurrentPosition = vi.fn((success: PositionSuccess, _error?: PositionErrorCallback | null, _options?: PositionOptions) => success({ coords: point, timestamp: 2000 }))
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
    await expect(captureGPS()).resolves.toEqual({ ...point, capturedAt: 2000 })
    expect(getCurrentPosition.mock.calls[0][2]).toEqual({ enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
  })
  it('explains permission denial and permits a later retry', async () => {
    vi.stubGlobal('isSecureContext', true)
    const getCurrentPosition = vi.fn((_success, error) => error({ code: 1 }))
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition } })
    await expect(captureGPS()).rejects.toThrow('permission is blocked')
    getCurrentPosition.mockImplementation(success => success({ coords: point, timestamp: 2000 }))
    await expect(captureGPS()).resolves.toMatchObject({ latitude: point.latitude })
  })
  it('does not request GPS on an insecure phone origin', async () => {
    vi.stubGlobal('isSecureContext', false)
    await expect(captureGPS()).rejects.toThrow('HTTPS')
  })
  it('rejects malformed device readings before saving them', async () => {
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('navigator', { geolocation: { getCurrentPosition: (success: PositionSuccess) => success({ coords: { ...point, latitude: NaN }, timestamp: 2000 }) } })
    await expect(captureGPS()).rejects.toThrow('invalid location')
  })
  it('orders camera proximity in geographic metres', () => {
    expect(gpsDistance(point, point)).toBe(0)
    expect(gpsDistance({ ...point, latitude: 0, longitude: 0 }, { ...point, latitude: 0, longitude: 1 })).toBeCloseTo(111195, -1)
  })
})
