import { useState } from 'react'
import { NativeVideo } from '../classroom/NativeVideoCanvas'
import type { NativeVideoBus, NativeRenderedFrame } from '../classroom/nativeVideo'
import { PushPin, VideoCameraSlash } from '@phosphor-icons/react'
import type { Incident } from '../classroom/contracts'
import { PoliceContactStatus } from '../emergency/PoliceContact'
import { validGPS } from '../location/gps'
import { TrackingOverlay } from './TrackingOverlay'
import { NativePoseHistory, nativeOverlayAligned } from './nativeTracking'
import { observedTracks, wallDetection, wallTracking } from './tracking'
import { alertLevel, cameraPlace, formatClock, formatElapsed, isActiveResponse, needsDecision, type WallCamera } from './model'

interface Props {
  nativeVideo?: NativeVideoBus
  camera: WallCamera
  events: Incident[]
  now: number
  pinned?: boolean
  selected?: boolean
  size?: 'tile' | 'thumb' | 'hero'
  onOpen?: () => void
  onRemove?: () => void
  removing?: boolean
}

const statusText = {
  live: 'Live',
  connecting: 'Connecting',
  offline: 'Offline',
  paused: 'Paused',
} as const

export function CameraTile({ camera, events, now, pinned, selected, size = 'tile', onOpen, onRemove, removing, nativeVideo }: Props) {
  const [nativePlaying, setNativePlaying] = useState(false)
  const [nativeFPS, setNativeFPS] = useState<number|null>(null)
  const [nativeFrame, setNativeFrame] = useState<NativeRenderedFrame|null>(null)
  const [poseHistory] = useState(() => new NativePoseHistory())
  if(nativeVideo && size !== 'thumb')poseHistory.add(camera,Date.now());else poseHistory.clear()
  const nativeResult=nativeFrame ? poseHistory.select(camera,nativeFrame,Date.now()) : null
  const nativeCamera={...camera,result:nativeResult}
  const level = alertLevel(camera.id, events)
  const flagged = events.find((e) => e.camera_id === camera.id && needsDecision(e))
  const incident = flagged ?? events.find(e => e.camera_id === camera.id && isActiveResponse(e)) ?? events.find(e => e.camera_id === camera.id)
  const police = incident?.police
  const title = `${camera.label} ${camera.name}`
  const tracking = wallTracking(camera, now)
  const detection = wallDetection(nativePlaying && nativeFrame ? { ...nativeCamera, preview: { timestampMs:nativeFrame.timestampMs, received:nativeFrame.renderedAt, width:nativeFrame.width, height:nativeFrame.height, generation:nativeFrame.generation } } : camera, now)
  const detectionLabel = camera.sample ? 'Sample footage' : `${detection.people ? `${detection.people} ${detection.people === 1 ? 'person' : 'people'} · ` : ''}${detection.label}`
  const body = (
    <>
      {size !== 'thumb' && (
        <header className="cm-tile-head">
          <strong>
            <span className="cm-camera-name">{camera.name}</span><small>{camera.label}</small>
          </strong>
          {camera.sample && <span className="cm-tag">Sample</span>}
          {pinned && (
            <span className="cm-pinned">
              <PushPin weight="fill" aria-hidden /> Pinned
            </span>
          )}
          <span className={`cm-status cm-status--${camera.status}`}>
            <i aria-hidden /> {statusText[camera.status]}
          </span>
          {(nativePlaying ? nativeFPS : camera.fps) != null && <span className="cm-fps" title="Video frames displayed per second">{nativePlaying ? nativeFPS : camera.fps} fps</span>}
        </header>
      )}
      {size !== 'thumb' && <span className="cm-location-stamp">{cameraPlace(camera) || 'Location not set'}{size === 'hero' && <small>{validGPS(camera.gps) ? 'Last shared location' : 'Location not shared'}</small>}</span>}
      <div className="cm-feed">
        {camera.status === 'offline' || !camera.image ? (
          <div className="cm-feed-empty">
            <VideoCameraSlash size={size === 'thumb' ? 18 : 28} aria-hidden />
            {size !== 'thumb' && (
              <span>
                {camera.status === 'offline'
                  ? 'Camera offline'
                  : 'Waiting for video'}
              </span>
            )}
          </div>
        ) : (
          <img src={camera.image} alt="" draggable={false} />
        )}
        {size !== 'thumb' && nativeVideo && camera.generation && camera.status === 'live' && !camera.preview?.analysisFrame && <NativeVideo bus={nativeVideo} cameraId={camera.id} generation={camera.generation} onPlaying={setNativePlaying} onFrame={setNativeFrame} onFPS={setNativeFPS} overlayMatches={frame => nativeOverlayAligned(nativeCamera,frame,nativeFrame,Date.now())}>
          {nativeFrame && nativeResult && <TrackingOverlay tracks={observedTracks(nativeResult.tracks)} poses={nativeResult.poses} width={nativeFrame.width} height={nativeFrame.height} />}
        </NativeVideo>}
        {!nativePlaying && (tracking.tracks.length > 0 || tracking.poses.length > 0) && camera.preview?.width && camera.preview?.height && <TrackingOverlay tracks={tracking.tracks} poses={tracking.poses} width={camera.preview.width} height={camera.preview.height} />}
        {size !== 'thumb' && <span className="cm-ai-state" title={tracking.detail || detection.action}>{detectionLabel}{camera.preview?.analysisFrame && <small>Earlier frame · {Math.max(0, (now - (camera.preview.received ?? now)) / 1000).toFixed(1)}s ago</small>}{!camera.sample && detection.state === 'limited' && <small>{detection.action}</small>}{!nativePlaying && tracking.label === 'AI delayed · boxes hidden' && <small>Video is ahead. Markings paused.</small>}</span>}
        {level === 'review' && flagged && size !== 'thumb' && (
          <span className="cm-flag">
            {flagged.model === 'test' ? 'Test alert' : 'Check this camera'} · {formatElapsed(now - flagged.received_at)}
          </span>
        )}
        {level === 'confirmed' && size !== 'thumb' && <span className="cm-flag cm-flag--confirmed">Confirmed incident</span>}
        {size !== 'thumb' && police && <span className="cm-police"><PoliceContactStatus police={police} /></span>}
        {size !== 'thumb' && camera.image && camera.status === 'live' && (
          <span className="cm-stamp" title="Current monitor time">{formatClock(now)} <span className="cm-sr-only">monitor time</span></span>
        )}
      </div>
      {size === 'thumb' && <span className="cm-thumb-label">{camera.label}</span>}
    </>
  )
  const className = `cm-tile cm-tile--${size} ${selected ? 'is-selected' : ''}`
  const tile = onOpen ? (
    <button
      type="button"
      className={className}
      data-alert={level ?? undefined}
      onClick={onOpen}
      aria-label={`${title}${level === 'review' ? ', needs review' : level === 'confirmed' ? ', confirmed incident' : ''}. ${level === 'review' || level === 'confirmed' ? 'Open incident review' : 'Open full camera view'}`}
      aria-pressed={selected || undefined}
    >
      {body}
    </button>
  ) : (
    <article className={className} data-alert={level ?? undefined} aria-label={title}>
      {body}
    </article>
  )
  return onRemove && !camera.sample && size !== 'thumb' ? <div className="cm-tile-shell">
    {tile}
    <button type="button" className="cm-btn cm-camera-remove" aria-label={`Remove ${camera.name}`} disabled={removing} onClick={onRemove}>{removing ? 'Removing…' : 'Remove'}</button>
  </div> : tile
}
