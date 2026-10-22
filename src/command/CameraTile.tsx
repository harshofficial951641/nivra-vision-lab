import { PushPin, VideoCameraSlash } from '@phosphor-icons/react'
import type { Incident } from '../classroom/contracts'
import { alertLevel, formatClock, formatElapsed, needsDecision, type WallCamera } from './model'

interface Props {
  camera: WallCamera
  events: Incident[]
  now: number
  pinned?: boolean
  selected?: boolean
  size?: 'tile' | 'thumb' | 'hero'
  onOpen?: () => void
}

const statusText = {
  live: 'Live',
  connecting: 'Connecting',
  offline: 'Offline',
  paused: 'Paused',
} as const

export function CameraTile({ camera, events, now, pinned, selected, size = 'tile', onOpen }: Props) {
  const level = alertLevel(camera.id, events)
  const flagged = events.find((e) => e.camera_id === camera.id && needsDecision(e))
  const title = `${camera.label} ${camera.name}`
  const body = (
    <>
      {size !== 'thumb' && (
        <header className="cm-tile-head">
          <strong>
            {camera.label} <span>{camera.name}</span>
          </strong>
          <span className="cm-tag">Phone</span>
          {pinned && (
            <span className="cm-pinned">
              <PushPin weight="fill" aria-hidden /> Pinned
            </span>
          )}
          <span className={`cm-status cm-status--${camera.status}`}>
            <i aria-hidden /> {statusText[camera.status]}
          </span>
          {camera.fps != null && <span className="cm-fps">{camera.fps} fps</span>}
        </header>
      )}
      <div className="cm-feed">
        {camera.status === 'offline' || !camera.image ? (
          <div className="cm-feed-empty">
            <VideoCameraSlash size={size === 'thumb' ? 18 : 28} aria-hidden />
            {size !== 'thumb' && (
              <span>
                {camera.status === 'offline'
                  ? camera.sample
                    ? 'Camera offline · Last seen 2m ago'
                    : 'Camera offline'
                  : 'Waiting for video'}
              </span>
            )}
          </div>
        ) : (
          <img src={camera.image} alt="" draggable={false} />
        )}
        {level === 'review' && flagged && size !== 'thumb' && (
          <span className="cm-flag">
            {flagged.model === 'test' ? 'Test alert' : 'Possible physical conflict'} · {formatElapsed(now - flagged.received_at)}
          </span>
        )}
        {level === 'confirmed' && size !== 'thumb' && <span className="cm-flag cm-flag--confirmed">Confirmed incident</span>}
        {size !== 'thumb' && camera.image && camera.status === 'live' && (
          <span className="cm-stamp">{formatClock(now)}</span>
        )}
      </div>
      {size === 'thumb' && <span className="cm-thumb-label">{camera.label}</span>}
    </>
  )
  const className = `cm-tile cm-tile--${size} ${selected ? 'is-selected' : ''}`
  return onOpen ? (
    <button
      type="button"
      className={className}
      data-alert={level ?? undefined}
      onClick={onOpen}
      aria-label={`${title}${level === 'review' ? ', possible physical conflict' : level === 'confirmed' ? ', confirmed incident' : ''}. Open on map`}
      aria-pressed={selected || undefined}
    >
      {body}
    </button>
  ) : (
    <article className={className} data-alert={level ?? undefined} aria-label={title}>
      {body}
    </article>
  )
}
