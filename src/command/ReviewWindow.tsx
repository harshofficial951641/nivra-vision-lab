import { useEffect, useId, useRef, useState } from 'react'
import { CheckCircle, WarningCircle, X } from '@phosphor-icons/react'
import { api, type Incident } from '../classroom/contracts'
import type { ClipBuffer } from './clipBuffer'
import { ClipPlayer, type PlayerFrame } from './ClipPlayer'
import { GoogleMap } from '../location/GoogleMap'
import { PoliceContact, PoliceContactStatus } from '../emergency/PoliceContact'
import {
  REASONS,
  rankGPSGuards,
  gpsStatus,
  formatClock,
  formatElapsed,
  incidentRef,
  isActiveResponse,
  needsDecision,
  reasonLabel,
  stageOf,
  type DismissReason,
  type ReviewAction,
  type ReviewPayload,
  type WallCamera,
} from './model'
import type { MapFloor, WallGuard } from './types'

interface Props {
  event: Incident
  cameras: WallCamera[]
  events: Incident[]
  now: number
  clips: ClipBuffer | null
  floors: MapFloor[]
  guards: WallGuard[]
  siteName?: string
  sample: boolean
  queue: number
  act: (action: ReviewAction, payload?: ReviewPayload) => Promise<void>
  close: () => void
}

const SAMPLE_CLIP = [
  { src: '/demo/mall/clip-04-a-approach.jpg', offset: 0 },
  { src: '/demo/mall/cam-04-atrium-east.jpg', offset: 6_000 },
  { src: '/demo/mall/clip-04-c-push.jpg', offset: 10_000 },
]

interface ServerClip {
  status: 'recording' | 'ready' | 'expired' | 'none'
  startMs: number
  peakMs: number
  endMs: number
  frames: { t: number; url: string }[]
}

/** Clip recorded by the service (RAM only). Polls while it is still recording. */
function useServerClip(event: Incident, enabled: boolean) {
  const [clip, setClip] = useState<ServerClip | null>(null)
  const status = event.clip?.status
  useEffect(() => {
    if (!enabled || !status || status === 'none') return
    let active = true
    let timer = 0
    const load = async () => {
      try {
        const next = await api<ServerClip>(`/events/${event.id}/clip`)
        if (!active) return
        setClip(next)
        if (next.status === 'recording') timer = window.setTimeout(load, 1500)
      } catch {
        if (active) timer = window.setTimeout(load, 4000)
      }
    }
    void load()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [enabled, event.id, status])
  return clip
}

function clipFor(
  event: Incident,
  camera: WallCamera | undefined,
  clips: ClipBuffer | null,
  sample: boolean,
  server: ServerClip | null,
) {
  const peakAt = event.received_at
  const startAt = peakAt - 10_000
  const endAt = peakAt + 8_000
  if (sample) {
    const frames: PlayerFrame[] =
      camera?.id === 'cam-04'
        ? SAMPLE_CLIP.map((f) => ({ src: f.src, at: startAt + f.offset }))
        : camera?.image
          ? [{ src: camera.image, at: startAt }]
          : []
    return { frames, startAt, peakAt, endAt, complete: true, note: 'Sample clip: generated stills, not real footage.' }
  }
  if (server && server.frames.length && server.status !== 'expired')
    return {
      frames: server.frames.map((f) => ({ src: f.url, at: f.t })),
      startAt: server.startMs,
      peakAt: server.peakMs,
      endAt: server.endMs,
      complete: server.status === 'ready',
      note: 'Recorded on the NIVRA computer, kept in memory only and deleted when the incident closes.',
    }
  const clip = clips?.get(event.id)
  if (clip && clip.frames.length)
    return {
      frames: clip.frames.map((f) => ({ src: f.blob, at: f.at })),
      startAt: clip.startAt,
      peakAt: clip.peakAt,
      endAt: clip.endAt,
      complete: clip.complete,
      note: 'Kept in this browser’s memory only. Cleared when the incident closes.',
    }
  return {
    frames: camera?.image ? [{ src: camera.image, at: startAt }] : [],
    startAt,
    peakAt,
    endAt,
    complete: true,
    note:
      event.model === 'test'
        ? 'Test alert: there is no recorded clip, so the live view is shown.'
        : 'No clip was recorded for this incident, so only the live view is shown.',
  }
}

export function ReviewWindow({ event, cameras, now, clips, guards, siteName, sample, queue, act, close }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [note, setNote] = useState('')
  const [reason, setReason] = useState<DismissReason | null>(null)
  const camera = cameras.find((c) => c.id === event.camera_id)
  const ranked = rankGPSGuards(guards, event.gps, now)
  const firstAvailable = ranked.find((r) => r.guard.status === 'available' && !(r.guard.id === event.guard && event.guard_declined_at))?.guard.id ?? null
  const [guard, setGuard] = useState<string | null>(firstAvailable)
  const [allGuards, setAllGuards] = useState(false)
  const [showDismiss, setShowDismiss] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const reasonGroup = useRef<HTMLDivElement>(null)
  const serverClip = useServerClip(event, !sample)
  const clip = clipFor(event, camera, clips, sample, serverClip)
  const stage = stageOf(event)
  const deciding = needsDecision(event)

  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [])

  // Count the review as started only when a person can see this window.
  const viewed = useRef(false)
  useEffect(() => {
    if (event.status !== 'open' || viewed.current) return
    const markViewed = () => {
      if (viewed.current || document.visibilityState !== 'visible') return
      viewed.current = true
      void act('view').catch(() => {
        viewed.current = false
      })
    }
    if (document.hasFocus()) markViewed()
    window.addEventListener('focus', markViewed)
    document.addEventListener('pointerdown', markViewed)
    return () => {
      window.removeEventListener('focus', markViewed)
      document.removeEventListener('pointerdown', markViewed)
    }
  }, [event.status, act])

  const run = async (action: ReviewAction, payload: ReviewPayload = {}, after?: () => void) => {
    setBusy(true)
    setError('')
    try {
      await act(action, payload)
      after?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'That action did not go through. Try again.')
    } finally {
      setBusy(false)
    }
  }
  const dismiss = () => {
    if (!reason) {
      setError('Pick why this is a false alarm first.')
      reasonGroup.current?.querySelector<HTMLInputElement>('input')?.focus()
      return
    }
    void run('dismiss', { reason, note }, close)
  }
  const keepWatching = () => {
    if (event.status === 'open') void run('view', {}, close)
    else close()
  }
  const signals = event.detail.split('\n').map((line) => line.trim()).filter(Boolean)
  const guardName = (id: string | null | undefined) => guards.find((g) => g.id === id)?.name ?? ''
  const chosen = ranked.find((r) => r.guard.id === guard)

  return (
    <dialog
      ref={dialog}
      className="cm-review"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault()
        close()
      }}
    >
      <header className="cm-review-head">
        <div>
          <h2 id={titleId}>
            {incidentRef(event)} · {event.model === 'test' ? 'Test alert' : event.decision === 'confirmed' ? 'Confirmed incident' : 'Check this moment'}
            {event.model === 'test' && <span className="cm-pill">Test · not a real incident</span>}
            <span className={`cm-pill cm-pill--${deciding ? 'amber' : stage === 'false_alarm' || stage === 'cleared' ? 'quiet' : 'red'}`}>
              {deciding ? 'Needs your review' : stage === 'false_alarm' ? 'False alarm' : stage === 'cleared' ? 'Closed' : 'Response in progress'}
            </span>
          </h2>
          <p className="cm-muted">
            {[siteName, camera?.name ?? event.camera_name, event.location].filter(Boolean).join(' / ')}
            {queue > 1 ? ` · ${queue - 1} more waiting` : ''}
          </p>
        </div>
        <div className="cm-review-time">
          <span className="cm-muted">Detected {formatClock(event.received_at)}</span>
          <strong>
            {formatElapsed(now - event.received_at)} <small>since detection</small>
          </strong>
        </div>
        <button type="button" className="cm-btn cm-btn--quiet cm-esc" onClick={close} aria-label="Close review window (Esc)">
          <X aria-hidden /> Close
        </button>
      </header>

      <div className="cm-review-body">
        <section className="cm-review-clip" aria-label="Incident clip">
          <ClipPlayer
            label={camera?.label ?? event.camera_name}
            frames={clip.frames}
            startAt={clip.startAt}
            peakAt={clip.peakAt}
            endAt={clip.endAt}
            complete={clip.complete}
            note={clip.note}
          />
          <details className="cm-review-details"><summary>Why this needs a look</summary>
          <ul className="cm-signals">
            {signals.map((signal) => (
              <li key={signal}>{signal}</li>
            ))}
          </ul>
          <p className="cm-muted cm-small">
            {sample
              ? 'Video quality: good · sample data'
              : camera?.fps != null
                ? `Analysis ${camera.fps} fps${camera.people != null ? ` · ${camera.people} people in view` : ''}`
                : 'Analysis rate unavailable'}
            {' · '}Movement alone cannot show intent. Please review the video.
          </p></details>
        </section>

        <section className="cm-review-map" aria-label="Location">
          <h3>Location & guards</h3>
          {deciding || isActiveResponse(event)
            ? <PoliceContact key={event.id} incidentId={event.id} cameraName={event.camera_name} location={event.location} police={event.police} role="reviewer" sample={sample} />
            : <PoliceContactStatus police={event.police} />}
          <details className="cm-review-details"><summary>View location on map</summary>
          <GoogleMap point={event.gps} label={event.camera_name} sample={sample} />
          <p className="cm-muted cm-small">This is the camera location when the alert started. Check the camera name and floor for indoor directions.</p></details>
          {(deciding || (isActiveResponse(event) && (!event.alerted_at || event.guard_declined_at))) && (
            <fieldset className="cm-guards">
              <legend>Choose a guard</legend>
              <details className="cm-review-details"><summary>How guards are ordered</summary><p className="cm-muted cm-small">Available guards with a location from the last 2 minutes appear nearest first, by straight-line distance. Floor names are set by staff.</p></details>
              {(allGuards ? ranked : ranked.slice(0, 3)).map(({ guard: g, meters }) => {
                const away = g.status !== 'available'
                return (
                  <label key={g.id} className={away ? 'is-disabled' : ''}>
                    <input
                      type="radio"
                      name="guard"
                      value={g.id}
                      checked={guard === g.id}
                      disabled={away || (g.id === event.guard && !!event.guard_declined_at)}
                      onChange={() => setGuard(g.id)}
                    />
                    <span className="cm-guard-id">{g.id}</span>
                    <span>{g.name}<small className="cm-guard-detail">{g.floorName || 'Floor not set'} · {gpsStatus(g.gps, now)}</small><small className="cm-guard-detail">{meters == null ? 'Distance unavailable' : `${Math.round(meters)} m straight-line`}</small></span>
                    <span className="cm-muted">
                      {g.online ? 'Online' : 'Offline'}
                    </span>
                    <span className={away ? 'cm-muted' : ''}>{away ? g.status === 'off' ? 'Off shift' : 'On break' : 'Available'}</span>
                  </label>
                )
              })}
              {ranked.length > 3 && (
                <button type="button" className="cm-link" onClick={() => setAllGuards((v) => !v)}>
                  {allGuards ? 'Show first 3' : `Show all ${ranked.length} guards`}
                </button>
              )}
            </fieldset>
          )}
          {isActiveResponse(event) && event.alerted_at && (
            <div className="cm-response-status" role="status">
              <strong>
                {event.guard} {guardName(event.guard)} ·{' '}
                {stage === 'on_scene'
                  ? `on scene for ${formatElapsed(now - (event.on_scene_at ?? now))}`
                  : stage === 'acknowledged'
                    ? `on the way (${formatElapsed(now - (event.guard_ack_at ?? now))})`
                    : stage === 'declined'
                      ? 'cannot respond. Choose another guard'
                      : `alerted ${formatElapsed(now - event.alerted_at)} ago, waiting for a reply`}
              </strong>
              {stage === 'alerted' && (event.escalated_at || now - event.alerted_at > 30_000) && (
                <span className="cm-warn">
                  <WarningCircle aria-hidden /> No reply after 30 seconds. Call the guard or choose another.
                </span>
              )}
            </div>
          )}
          {!deciding && !isActiveResponse(event) && (
            <div className="cm-response-status" role="status">
              <CheckCircle aria-hidden />
              <strong>
                {event.decision === 'false_alarm'
                  ? `Logged as false alarm · ${reasonLabel(event.reason)}`
                  : !event.decision ? 'Alert closed without a decision' : `Situation clear · logged at ${formatClock(event.updated_at)}`}
              </strong>
            </div>
          )}
        </section>
      </div>

      {error && (
        <p className="cm-error" role="alert">
          {error}
        </p>
      )}

      {deciding ? (
        <footer className="cm-decide">
          <label className="cm-note">
            <span className="cm-sr-only">Note for the log</span>
            <input
              value={note}
              maxLength={280}
              placeholder="Add a note (optional)"
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="cm-decide-row">
            <div className="cm-false">
              <button type="button" className="cm-btn" disabled={busy} aria-expanded={showDismiss} onClick={() => setShowDismiss(value => !value)}>
                False alarm
              </button>
              {showDismiss && <div className="cm-dismiss-panel"><p>What happened?</p><div ref={reasonGroup} role="radiogroup" aria-label="False alarm reason" className="cm-chips">
                {REASONS.map((r) => (
                  <label key={r.id} className={`cm-chip ${reason === r.id ? 'is-on' : ''}`}>
                    <input
                      type="radio"
                      name="reason"
                      value={r.id}
                      checked={reason === r.id}
                      onChange={() => {
                        setReason(r.id)
                        setError('')
                      }}
                    />
                    {r.label}
                  </label>
                ))}
              </div><button type="button" className="cm-btn" disabled={busy} onClick={dismiss}>Save false alarm</button></div>}
            </div>
            <div className="cm-confirm">
              <button type="button" className="cm-btn" disabled={busy} title="Close this alert without marking it confirmed or false alarm" onClick={() => void run('close', {}, close)}>
                Close alert
              </button>
              <button type="button" className="cm-btn" disabled={busy} onClick={keepWatching}>
                Keep watching
              </button>
              <button type="button" className="cm-btn cm-btn--dark" disabled={busy} onClick={() => void run('confirm', { note })}>
                Confirm only
              </button>
              <button
                type="button"
                className="cm-btn cm-btn--dark"
                disabled={busy || !guard}
                onClick={() => void run('confirm', { note, guard: guard ?? undefined })}
              >
                {guard ? `Confirm & send ${guard}` : 'Confirm & send guard'}
              </button>
            </div>
          </div>
        </footer>
      ) : (
        <footer className="cm-decide cm-decide--response">
          {isActiveResponse(event) ? (
            <>
              <span className="cm-muted">
                {chosen && (!event.alerted_at || event.guard_declined_at)
                  ? `${chosen.guard.id} will receive the camera location and directions.`
                  : 'Updates arrive from the guard’s phone. You can also update them here.'}
              </span>
              <div className="cm-confirm">
                {(!event.alerted_at || event.guard_declined_at) && (
                  <button
                    type="button"
                    className="cm-btn cm-btn--dark"
                    disabled={busy || !guard}
                    onClick={() => void run('alert', { guard: guard ?? undefined })}
                  >
                    {guard ? `Send ${guard}` : 'Send a guard'}
                  </button>
                )}
                {event.alerted_at && !event.on_scene_at && !event.guard_declined_at && (
                  <button type="button" className="cm-btn" disabled={busy} onClick={() => void run('on_scene')}>
                    Mark {event.guard} on scene
                  </button>
                )}
                <button type="button" className="cm-btn cm-btn--dark" disabled={busy} onClick={() => void run('clear', {}, close)}>
                  Situation clear
                </button>
                <button type="button" className="cm-btn" onClick={close}>
                  Back to wall
                </button>
              </div>
            </>
          ) : (
            <div className="cm-confirm">
              <button type="button" className="cm-btn cm-btn--dark" onClick={close}>
                Back to wall
              </button>
            </div>
          )}
        </footer>
      )}
    </dialog>
  )
}
