import { validGPS, type GPSLocation } from './gps'

/** Share the newest fix at most every ten seconds, with only one write in flight. */
export function watchGPS({ save, onSaved, onError, interval = 10_000 }: {
  save: (point: GPSLocation) => Promise<unknown>
  onSaved: (point: GPSLocation) => void
  onError: (message: string) => void
  interval?: number
}) {
  let stopped = false
  let watchId: number | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: GPSLocation | null = null
  let newestAt = -Infinity
  let lastSent = -Infinity
  let writing = false
  const stop = () => {
    stopped = true
    if (watchId !== null) navigator.geolocation.clearWatch(watchId)
    if (timer !== null) clearTimeout(timer)
    timer = null
    pending = null
  }
  const flush = async () => {
    if (stopped || writing || !pending) return
    const delay = interval - (Date.now() - lastSent)
    if (delay > 0) {
      timer ??= setTimeout(() => { timer = null; void flush() }, delay)
      return
    }
    const point = pending
    pending = null
    writing = true
    lastSent = Date.now()
    try {
      await save(point)
      if (!stopped) onSaved(point)
    } catch (reason) {
      if (!stopped) {
        onError(reason instanceof Error ? reason.message : 'Location could not be shared. Check the connection and retry.')
        // Retry the newest reading, even if the device is stationary.
        pending ??= point
      }
    } finally {
      writing = false
      if (!stopped) void flush()
    }
  }
  if (!window.isSecureContext || !navigator.geolocation) {
    onError(!window.isSecureContext ? 'Location sharing needs HTTPS. Open the secure pairing link.' : 'This phone does not support location sharing.')
    return stop
  }
  watchId = navigator.geolocation.watchPosition(({ coords, timestamp }) => {
    if (stopped) return
    const point = { latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy, capturedAt: timestamp }
    if (!validGPS(point)) return onError('This phone returned an invalid location. Check location services, then retry.')
    if (point.capturedAt <= newestAt) return
    newestAt = point.capturedAt
    pending = point
    void flush()
  }, error => {
    if (stopped) return
    onError(error.code === 1 ? 'Location permission is blocked. Allow location in your browser settings, then retry.'
      : error.code === 3 ? 'Location timed out. Move near a window or outdoors. Still trying…'
        : 'Location is unavailable. Check location services on this phone. Still trying…')
    if (error.code === 1) stop()
  }, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
  if (stopped) navigator.geolocation.clearWatch(watchId)
  return stop
}
