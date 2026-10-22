export interface GPSLocation {
  latitude: number
  longitude: number
  /** Horizontal accuracy reported by the device, in metres. */
  accuracy: number
  capturedAt: number
}

export function validGPS(point: GPSLocation | null | undefined): point is GPSLocation {
  return !!point && Number.isFinite(point.latitude) && Math.abs(point.latitude) <= 90 &&
    Number.isFinite(point.longitude) && Math.abs(point.longitude) <= 180 &&
    Number.isFinite(point.accuracy) && point.accuracy >= 0 && Number.isFinite(point.capturedAt) && point.capturedAt >= 0
}

export function coordinates(point: GPSLocation) {
  return `${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)}`
}

export function googleMapsURL(point: GPSLocation, directions = false) {
  const params = new URLSearchParams({ api: '1' })
  if (directions) {
    params.set('destination', `${point.latitude},${point.longitude}`)
    params.set('travelmode', 'walking')
  } else params.set('query', `${point.latitude},${point.longitude}`)
  return `https://www.google.com/maps/${directions ? 'dir' : 'search'}/?${params}`
}

export function captureGPS(): Promise<GPSLocation> {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext) return reject(new Error('Location needs HTTPS. Open the secure camera pairing link.'))
    if (!navigator.geolocation) return reject(new Error('This device does not support location sharing.'))
    navigator.geolocation.getCurrentPosition(
      ({ coords, timestamp }) => {
        const point = { latitude: coords.latitude, longitude: coords.longitude, accuracy: coords.accuracy, capturedAt: timestamp }
        if (validGPS(point)) resolve(point)
        else reject(new Error('This phone returned an invalid location. Check location services, then retry.'))
      },
      (error) => reject(new Error(error.code === 1
        ? 'Location permission is blocked. Allow location in your browser settings, then retry.'
        : error.code === 3 ? 'Location timed out. Move near a window or outdoors, then retry.'
          : 'Location is unavailable. Check location services on this phone, then retry.')),
      { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
    )
  })
}

/** Straight-line distance, used only to order nearby cameras, never as a walking ETA. */
export function gpsDistance(a: GPSLocation, b: GPSLocation) {
  const rad = (degrees: number) => degrees * Math.PI / 180
  const h = Math.sin(rad(b.latitude - a.latitude) / 2) ** 2 +
    Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(rad(b.longitude - a.longitude) / 2) ** 2
  return 6371000 * 2 * Math.atan2(Math.sqrt(Math.min(1, h)), Math.sqrt(Math.max(0, 1 - h)))
}
