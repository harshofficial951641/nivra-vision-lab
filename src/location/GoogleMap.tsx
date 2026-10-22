import { useState } from 'react'
import { coordinates, googleMapsURL, validGPS, type GPSLocation } from './gps'
import './location.css'

export function GoogleMap({ point, label, sample = false, kind = 'camera' }: { point?: GPSLocation | null; label: string; sample?: boolean; kind?: 'camera' | 'guard' }) {
  const [attempt, setAttempt] = useState(0)
  if (!validGPS(point)) return (
    <div className="cm-empty-map gps-empty">
      <strong>{sample ? 'This is a sample location.' : 'Location not shared yet.'}</strong>
      <p>{kind === 'guard' ? 'Start the guard’s shift and allow location access.' : 'Start the camera phone and allow location access.'} You’ll see it here.</p>
    </div>
  )
  const query = `${point.latitude},${point.longitude}`
  const key = import.meta.env.VITE_GOOGLE_MAPS_EMBED_KEY
  const src = key
    ? `https://www.google.com/maps/embed/v1/place?${new URLSearchParams({ key, q: query, zoom: '18' })}`
    : `https://maps.google.com/maps?${new URLSearchParams({ q: query, z: '18', output: 'embed' })}`
  return (
    <div className="gps-map">
      <iframe key={`${src}:${attempt}`} title={`Google Maps · ${label}`} src={src} loading="lazy" allowFullScreen
        referrerPolicy="strict-origin-when-cross-origin" {...{ credentialless: '' }} />
      <div className="gps-map-footer">
        <a href={googleMapsURL(point, true)} target="_blank" rel="noreferrer">Get directions ↗</a>
        <a href={googleMapsURL(point)} target="_blank" rel="noreferrer">Open Google Maps ↗</a>
      </div>
      <details className="gps-note"><summary>About this location</summary><p>Updated {new Date(point.capturedAt).toLocaleString()}. A phone’s location can be less accurate indoors.</p><p>{coordinates(point)} · within about {Math.ceil(point.accuracy)} m</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Reload map</button></details>
    </div>
  )
}
