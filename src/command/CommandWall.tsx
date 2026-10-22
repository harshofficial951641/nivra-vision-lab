import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode, type CSSProperties } from 'react'
import {
  ArrowsOut,
  ArrowLeft,
  ArrowRight,
  PlayCircle,
  PushPin,
  SpeakerHigh,
  SpeakerSlash,
  GearSix,
  SignOut,
  UsersThree,
  WarningCircle,
  X,
} from '@phosphor-icons/react'
import { api, type Incident } from '../classroom/contracts'
import { AlertPing } from './AlertPing'
import { CameraTile } from './CameraTile'
import { Brand } from '../ui/Brand'
import { GoogleMap } from '../location/GoogleMap'
import { coordinates, googleMapsURL, validGPS } from '../location/gps'
import { ResponseClock } from './ResponseClock'
import { ReviewWindow } from './ReviewWindow'
import {
  focusIncident,
  cameraPlace,
  gpsStatus,
  formatClock,
  incidentRef,
  isActiveResponse,
  needsDecision,
  type ReviewAction,
  type ReviewPayload,
  type WallCamera,
} from './model'
import { useOptionalSession } from '../auth/context'
import type { WallGuard } from './types'
import { useCommand } from './useCommand'
import './command.css'

const PIN_KEY = 'nivra.wall.pinned'
const readPins = (): string[] => {
  try {
    const value = JSON.parse(localStorage.getItem(PIN_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter((v) => typeof v === 'string') : []
  } catch {
    return []
  }
}

function useNow(interval = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), interval)
    return () => clearInterval(timer)
  }, [interval])
  return now
}

function Modal({ title, close, children, full, navigate }: { title: string; close: () => void; children: ReactNode; full?: boolean; navigate?: (direction: number) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = ref.current
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [])
  return (
    <dialog
      ref={ref}
      className={`cm-modal ${full ? 'cm-modal--camera' : ''}`}
      aria-label={title}
      onKeyDown={(event) => {
        if (!navigate || event.altKey || event.metaKey || event.ctrlKey || event.shiftKey || (event.target instanceof HTMLElement && event.target.matches('input, textarea, select, [contenteditable="true"]'))) return
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          event.preventDefault()
          navigate(event.key === 'ArrowLeft' ? -1 : 1)
        }
      }}
      onCancel={(e) => {
        e.preventDefault()
        close()
      }}
    >
      <header>
        <h2>{title}</h2>
        <button type="button" className="cm-icon-btn" aria-label="Close" onClick={close}>
          <X aria-hidden />
        </button>
      </header>
      {children}
    </dialog>
  )
}

interface CameraFocusProps {
  nativeVideo?: import('../classroom/nativeVideo').NativeVideoBus
  cameras: WallCamera[]
  cameraId: string
  events: Incident[]
  now: number
  pinned: string[]
  change: (id: string) => void
  togglePin: (id: string) => void
  openMap: (id: string) => void
  close: () => void
}

export function CameraFocus({ cameras, cameraId, events, now, pinned, change, togglePin, openMap, close, nativeVideo }: CameraFocusProps) {
  const start = useRef<{ x: number; y: number } | null>(null)
  const frame = useRef<HTMLDivElement>(null)
  const index = cameras.findIndex(camera => camera.id === cameraId)
  const camera = cameras[index]
  const navigate = (direction: number) => {
    if (cameras.length > 1 && index >= 0) change(cameras[(index + direction + cameras.length) % cameras.length].id)
  }
  const resetDrag = () => { frame.current?.style.setProperty('--swipe-x', '0px') }
  if (!camera) return null
  return <Modal title={camera.name} close={close} full navigate={navigate}>
    <div className="cm-focus-stage" role="group" aria-label="Camera footage"
      onTouchStart={event => { start.current = event.touches.length === 1 ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null }}
      onTouchMove={event => {
        if (!start.current || event.touches.length !== 1) { start.current = null; resetDrag(); return }
        const dx = event.touches[0].clientX - start.current.x, dy = event.touches[0].clientY - start.current.y
        if (Math.abs(dx) > Math.abs(dy) * 1.5) frame.current?.style.setProperty('--swipe-x', `${Math.max(-32, Math.min(32, dx * .2))}px`)
      }}
      onTouchCancel={() => { start.current = null; resetDrag() }}
      onTouchEnd={event => {
        const origin = start.current
        start.current = null; resetDrag()
        if (!origin || event.changedTouches.length !== 1) return
        const dx = event.changedTouches[0].clientX - origin.x, dy = event.changedTouches[0].clientY - origin.y
        if (Math.abs(dx) >= 64 && Math.abs(dx) > Math.abs(dy) * 1.5) navigate(dx < 0 ? 1 : -1)
      }}>
      <div className="cm-focus-frame" key={camera.id} ref={frame}>
        <CameraTile nativeVideo={nativeVideo} camera={camera} events={events} now={now} size="hero" pinned={pinned.includes(camera.id)} />
      </div>
    </div>
    <footer className="cm-full-actions">
      <div className="cm-camera-pager" aria-label="Browse cameras">
        <button type="button" className="cm-btn" aria-label="Previous camera" disabled={cameras.length < 2} onClick={() => navigate(-1)}><ArrowLeft aria-hidden /> Previous</button>
        <span aria-live="polite">{index + 1} / {cameras.length}</span>
        <button type="button" className="cm-btn" aria-label="Next camera" disabled={cameras.length < 2} onClick={() => navigate(1)}>Next <ArrowRight aria-hidden /></button>
      </div>
      {cameras.length > 1 && <span className="cm-swipe-hint">Swipe to change camera</span>}
      <button type="button" className="cm-btn" onClick={() => openMap(camera.id)}>Map</button>
      <details className="cm-camera-info"><summary>Details</summary><div>
        <p>{cameraPlace(camera) || 'Location not set'}</p>
        <p>{gpsStatus(camera.gps, now)}{validGPS(camera.gps) && ` · ${coordinates(camera.gps)}`}</p>
        <button type="button" className="cm-btn" aria-pressed={pinned.includes(camera.id)} onClick={() => togglePin(camera.id)}><PushPin aria-hidden /> {pinned.includes(camera.id) ? 'Unpin camera' : 'Pin camera'}</button>
      </div></details>
    </footer>
  </Modal>
}

function GuardRoster({ guards, sample, admin, now }: { guards: WallGuard[]; sample: boolean; admin: boolean; now: number }) {
  return (
    <div className="cm-pairing">
      {!guards.length ? (
        <p className="cm-muted">No guards yet. {admin ? 'Add a guard in Setup.' : 'Ask the owner to add a guard.'}</p>
      ) : (
        <ul>
          {guards.map((guard) => (
            <li key={guard.id}>
              <span className="cm-guard-id">{guard.id}</span>
              <span>
                {guard.name}
                <small className="cm-guard-detail">{guard.floorName || 'Floor not set'} · {gpsStatus(guard.gps, now)}</small>
                {validGPS(guard.gps) && <a className="cm-guard-detail" href={googleMapsURL(guard.gps)} target="_blank" rel="noreferrer">View last location in Google Maps</a>}
              </span>
              <span className="cm-muted">
                {guard.status === 'available' ? 'On shift' : guard.status === 'break' ? 'On break' : 'Off shift'}
                {guard.online != null && ` · ${guard.online ? 'online' : 'offline'}`}
                {guard.push != null && ` · alerts ${guard.push ? 'on' : 'off'}`}
              </span>
              {sample ? (
                <a className="cm-btn" href={`/guard?demo=1&guard=${guard.id}`} target="_blank" rel="noreferrer">
                  Open guard app
                </a>
              ) : (
                <span />
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="cm-muted">
        {sample
          ? 'Sample guard links open the guard app in another tab on this computer.'
          : 'Guards use their paired phones to receive alerts and update their status.'}
      </p>
      {admin && !sample && (
        <a className="cm-btn cm-btn--dark" href="/setup#guards">
          Manage guards
        </a>
      )}
    </div>
  )
}

export default function CommandWall() {
  const sample = new URLSearchParams(location.search).get('demo') === '1'
  const data = useCommand(sample)
  const { events, guards, floors } = data
  const [removed, setRemoved] = useState<Set<string>>(() => new Set())
  const cameras = useMemo(() => data.cameras.filter(camera => !removed.has(camera.id)), [data.cameras, removed])
  const liveCount = data.connection === 'connected' || sample ? cameras.filter(camera => camera.status === 'live').length : 0
  // Only an explicit unpaired record with no stream history is a saved slot.
  // Keep unknown older snapshots and genuine disconnected feeds on the wall.
  const savedCameras = useMemo(() => cameras.filter(camera => camera.paired === false && !camera.generation && !camera.image && camera.status !== 'live' && !events.some(event => event.camera_id === camera.id && (needsDecision(event) || isActiveResponse(event)))), [cameras, events])
  const savedIds = useMemo(() => new Set(savedCameras.map(camera => camera.id)), [savedCameras])
  const session = useOptionalSession()
  const admin = session?.me?.role === 'admin'
  const canManage = admin && !sample
  const [removing, setRemoving] = useState<Set<string>>(() => new Set())
  const deleting = useRef(new Set<string>())
  const [removeError, setRemoveError] = useState<{camera: WallCamera; message: string} | null>(null)
  const now = useNow()
  const [mode, setMode] = useState<'map' | 'all'>('all')
  const [selected, setSelected] = useState<string | null>(null)
  const [selectedGuard, setSelectedGuard] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string[]>(readPins)
  const [reviewing, setReviewing] = useState<string | null>(null)
  const [modal, setModal] = useState<'guards' | { full: string } | null>(null)
  const removeCamera = async (camera: WallCamera, retry = false) => {
    if (!canManage || deleting.current.has(camera.id) || removed.has(camera.id)) return
    if (!retry && !window.confirm(`Remove ${camera.name}? Its phone will disconnect. Previous alerts stay in history.`)) return
    deleting.current.add(camera.id)
    setRemoving(previous => new Set(previous).add(camera.id))
    setRemoveError(null)
    try {
      await api(`/cameras/${encodeURIComponent(camera.id)}`, 'DELETE')
      setRemoved(previous => new Set(previous).add(camera.id))
      setModal(previous => typeof previous === 'object' && previous?.full === camera.id ? null : previous)
      setSelected(previous => previous === camera.id ? null : previous)
    } catch (reason) {
      setRemoveError({camera, message: reason instanceof Error ? reason.message : 'Could not remove this camera.'})
    } finally {
      deleting.current.delete(camera.id)
      setRemoving(previous => {const next = new Set(previous); next.delete(camera.id); return next})
    }
  }
  const [sound, setSound] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [fullscreenError, setFullscreenError] = useState('')
  const appRef = useRef<HTMLDivElement>(null)
  const tone = useRef<AlertPing | null>(null)
  const seen = useRef<Set<string> | null>(null)

  useEffect(() => {
    const onFullscreen = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onFullscreen)
    return () => document.removeEventListener('fullscreenchange', onFullscreen)
  }, [])
  const toggleFullscreen = async () => {
    setFullscreenError('')
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else if (appRef.current?.requestFullscreen) await appRef.current.requestFullscreen()
      else setFullscreenError('Browser fullscreen is unavailable here. The wall still fills this window.')
    } catch {
      setFullscreenError('This browser could not enter fullscreen. The wall still fills this window.')
    }
  }

  useEffect(() => {
    localStorage.setItem(PIN_KEY, JSON.stringify(pinned))
  }, [pinned])

  const queue = useMemo(
    () => events.filter(needsDecision).sort((a, b) => a.received_at - b.received_at),
    [events],
  )
  const active = useMemo(() => events.filter(isActiveResponse), [events])
  const reviewEvent = events.find((e) => e.id === reviewing) ?? null
  useEffect(() => {
    if (reviewing) setModal(null)
  }, [reviewing])

  // Never open a review or move focus until the operator chooses it.
  useEffect(() => {
    if (reviewing && !events.some(event => event.id === reviewing)) setReviewing(null)
  }, [events, reviewing])

  // Keep IDs across snapshot removal/reappearance so reconnects cannot ring twice.
  useEffect(() => {
    if (!seen.current) { seen.current = new Set(events.map(event => event.id)); return }
    for (const event of events) {
      if (!seen.current.has(event.id) && needsDecision(event) && sound) void tone.current?.play()
      seen.current.add(event.id)
    }
  }, [events, sound])
  useEffect(() => () => tone.current?.dispose(), [])
  const toggleSound = async () => {
    if (sound) {
      setSound(false)
      tone.current?.stop()
      return
    }
    tone.current ??= new AlertPing()
    setSound(await tone.current.prime())
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || document.querySelector('dialog[open]')) return
      if (mode === 'map') setMode('all')
      setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mode])

  // Preserve the operator's spatial memory as alerts and people counts change.
  const cameraOrder = useRef<string[]>([])
  const ordered = useMemo(() => {
    const present = new Set(cameras.map(camera => camera.id))
    cameraOrder.current = cameraOrder.current.filter(id => present.has(id))
    for (const camera of cameras) if (!cameraOrder.current.includes(camera.id)) cameraOrder.current.push(camera.id)
    const positions = new Map(cameraOrder.current.map((id, index) => [id, index]))
    return cameras.filter(camera => !savedIds.has(camera.id)).sort((a, b) => positions.get(a.id)! - positions.get(b.id)!)
  }, [cameras, savedIds])
  const focus = focusIncident(events, now)
  const selectedCamera = cameras.find((c) => c.id === selected) ?? null
  const mapCamera = selectedCamera ?? cameras.find(c => c.id === focus?.camera_id) ?? cameras.find(c => c.gps) ?? cameras[0]
  const mapGuard = guards.find(g => g.id === selectedGuard) ?? null
  const mapPoint = mapGuard ? mapGuard.gps : mapCamera?.gps
  const mapLabel = mapGuard ? `${mapGuard.id} · ${mapGuard.name}` : mapCamera?.name ?? 'Camera'
  const mapDetails = mapGuard ? mapGuard.floorName || 'Floor not set' : mapCamera ? cameraPlace(mapCamera) || 'Location not set' : ''
  const unlocated = cameras.filter(c => !c.gps).length
  const selectCamera = useCallback((id: string) => {
    const incident = events.find(event => event.camera_id === id && needsDecision(event))
      ?? events.find(event => event.camera_id === id && isActiveResponse(event))
    if (incident) { setReviewing(incident.id); return }
    setSelected(id)
    setModal({ full: id })
  }, [events])
  const act = useCallback(
    (event: Incident) => (action: ReviewAction, payload?: ReviewPayload) => data.review(event, action, payload),
    [data],
  )
  const closeReview = () => {
    setReviewing(null)
  }
  const openReview = (id: string) => {
    setReviewing(id)
  }
  const togglePin = (id: string) =>
    setPinned((list) => (list.includes(id) ? list.filter((p) => p !== id) : [...list, id]))

  const connectionLabel = sample
    ? 'Sample workspace'
    : data.connection === 'connected'
      ? `${liveCount} live ${liveCount === 1 ? 'camera' : 'cameras'}`
      : data.connection === 'connecting'
        ? 'Connecting…'
        : 'Disconnected'

  return (
    <div className="cm-app" ref={appRef}>
      <a className="cm-skip" href="#cm-main">
        Skip to cameras
      </a>
      <header className="cm-top">
        <a className="cm-brand" href={sample ? '/wall?demo=1' : '/wall'}>
          <Brand compact />
        </a>
        <span className="cm-site" title={data.siteName}>
          {data.siteName}
        </span>
        <span className={`cm-pill ${!sample && data.connection !== 'connected' ? 'cm-pill--amber' : ''}`} role="status">
          {connectionLabel}
        </span>
        <nav className="cm-view-switch" aria-label="Wall view">
          <button className="cm-btn" aria-pressed={mode === 'all'} onClick={() => setMode('all')}>Cameras <span>{liveCount} live</span></button>
          <button className="cm-btn" aria-pressed={mode === 'map'} onClick={() => setMode('map')}>Map</button>
        </nav>
        <div className="cm-top-actions">
          {canManage && <a className="cm-btn" href="/setup#cameras">Add camera</a>}
          {(queue.length > 0 || active.length > 0) && <button className="cm-btn cm-pill--red" onClick={() => openReview((queue[0] ?? active[0]).id)}>{queue.length + active.length} open alert{queue.length + active.length === 1 ? '' : 's'}</button>}
          <details className="cm-more" onClick={event => { if ((event.target as HTMLElement).closest('button, a')) event.currentTarget.open = false }} onKeyDown={event => { if (event.key === 'Escape' && event.currentTarget.open) { event.stopPropagation(); event.preventDefault(); event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus() } }}>
            <summary>More</summary><div className="cm-more-menu">
          <button className="cm-icon-btn" aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'} title={fullscreen ? 'Exit fullscreen' : 'Fullscreen wall'} onClick={() => void toggleFullscreen()}><ArrowsOut aria-hidden /> {fullscreen ? 'Exit fullscreen' : 'Fullscreen'}</button>
          {sample && (
            <>
              <button type="button" className="cm-btn cm-btn--dark" onClick={data.runSample}>
                <PlayCircle aria-hidden /> Run sample incident
              </button>
              <button type="button" className="cm-btn" onClick={data.resetSample}>
                Reset
              </button>
            </>
          )}
          <button type="button" className="cm-btn" onClick={() => setModal('guards')}>
            <UsersThree aria-hidden /> Guards
          </button>
          {admin && (
            <a className="cm-btn" href="/setup">
              <GearSix aria-hidden /> Setup
            </a>
          )}
          {session?.me && session.me.workspace?.ownerVerification !== 'unverified' && (
            <button
              type="button"
              className="cm-icon-btn"
              aria-label={`Sign out ${session.me.name ?? ''}`.trim()}
              title={`${session.me.name ?? session.me.email ?? 'Signed in'} · sign out`}
              onClick={() => void session.signOut()}
            >
              <SignOut aria-hidden /> Sign out
            </button>
          )}
          <button
            type="button"
            className="cm-icon-btn"
            aria-label={sound ? 'Mute incident sound' : 'Turn on incident sound'}
            aria-pressed={sound}
            onClick={() => void toggleSound()}
          >
            {sound ? <SpeakerHigh aria-hidden /> : <SpeakerSlash aria-hidden />} {sound ? 'Mute alerts' : 'Alert sound'}
          </button>
            </div>
          </details>
          <time className="cm-clock-now">{formatClock(now)}</time>
        </div>
      </header>

      {sample && (
        <p className="cm-banner">
          <strong>Sample workspace.</strong> Example footage only. No live cameras.
        </p>
      )}
      {!sample && (data.connection !== 'connected' || data.error) && (
        <p className="cm-banner cm-banner--warn" role="alert">
          <WarningCircle aria-hidden /> {data.error || 'Reconnecting. Live cameras and alerts will return shortly.'}
        </p>
      )}
      {savedCameras.length > 0 && <details className="cm-banner cm-saved-cameras">
        <summary>{savedCameras.length} saved {savedCameras.length === 1 ? 'camera is' : 'cameras are'} waiting for a phone</summary>
        <ul>{savedCameras.map(camera => <li key={camera.id}><span>{camera.name} · Waiting for phone</span> <a href="/setup#cameras">Connect phone</a>{canManage && <button type="button" className="cm-btn" aria-label={`Remove ${camera.name}`} disabled={removing.has(camera.id)} onClick={() => void removeCamera(camera)}>{removing.has(camera.id) ? 'Removing…' : 'Remove'}</button>}</li>)}</ul>
        <a href="/setup#cameras">Manage saved cameras</a>
      </details>}

      {removeError && <p className="cm-banner cm-banner--warn" role="alert">Could not remove {removeError.camera.name}. {removeError.message} <button type="button" className="cm-btn" disabled={removing.has(removeError.camera.id)} onClick={() => void removeCamera(removeError.camera, true)}>Retry removal</button></p>}
      {fullscreenError && <p className="cm-banner cm-banner--warn" role="status">{fullscreenError}</p>}
      <main id="cm-main" className={`cm-main cm-main--${mode}`} inert={reviewEvent ? true : undefined}>
        {mode === 'map' ? (
          <>
            <section className="cm-map-panel" aria-labelledby="map-heading">
              <header>
                <h2 id="map-heading">Locations</h2>
              </header>
              <div className="gps-picker" aria-label="Choose camera location">
                {cameras.map(camera => <button key={camera.id} className="cm-btn" aria-pressed={!mapGuard && mapCamera?.id === camera.id} onClick={() => { setSelected(camera.id); setSelectedGuard(null) }}>
                  {camera.label} · {camera.gps ? camera.name : 'Location waiting'}
                </button>)}
              </div>
              <div className="gps-picker" aria-label="Choose guard location">
                {guards.map(guard => <button key={guard.id} className="cm-btn" aria-pressed={mapGuard?.id === guard.id} onClick={() => { setSelectedGuard(guard.id); setSelected(null) }}>{guard.id} · {guard.name}</button>)}
              </div>
              <p className="cm-map-person"><strong>{mapLabel}</strong><span>{mapDetails}</span><small>{gpsStatus(mapPoint, now)}</small></p>
              <GoogleMap point={mapPoint} label={mapLabel} kind={mapGuard ? 'guard' : 'camera'} sample={sample} />
              <p className="cm-hint" aria-live="polite">
                {unlocated ? `${unlocated} camera${unlocated === 1 ? '' : 's'} waiting for location. Allow location on the camera phone.` : 'Choose a camera or guard to see their location.'}
              </p>
            </section>

            <aside className="cm-side">
              {selectedCamera ? (
                <section className="cm-selected" aria-labelledby="selected-heading">
                  <header>
                    <h2 id="selected-heading">
                      {selectedCamera.label} · {selectedCamera.name}
                    </h2>
                    <button type="button" className="cm-icon-btn" aria-label="Close camera view" onClick={() => setSelected(null)}>
                      <X aria-hidden />
                    </button>
                  </header>
                  <CameraTile onRemove={canManage ? () => void removeCamera(selectedCamera) : undefined} removing={removing.has(selectedCamera.id)} nativeVideo={modal || reviewEvent ? undefined : data.nativeVideo} camera={selectedCamera} events={events} now={now} size="hero" pinned={pinned.includes(selectedCamera.id)} />
                  <div className="cm-selected-foot">
                    <span className="cm-muted">
                      {cameraPlace(selectedCamera)} · {gpsStatus(selectedCamera.gps, now)}
                    </span>
                    <button type="button" className="cm-btn" aria-pressed={pinned.includes(selectedCamera.id)} onClick={() => togglePin(selectedCamera.id)}>
                      <PushPin aria-hidden /> {pinned.includes(selectedCamera.id) ? 'Unpin' : 'Pin to wall'}
                    </button>
                    <button type="button" className="cm-btn cm-btn--dark" onClick={() => selectCamera(selectedCamera.id)}>
                      <ArrowsOut aria-hidden /> Open full view
                    </button>
                  </div>
                  <div className="cm-thumbs" role="list" aria-label="Wall cameras">
                    {ordered.slice(0, 4).map((camera) => (
                      <div role="listitem" key={camera.id}>
                        <CameraTile
                          nativeVideo={modal || reviewEvent ? undefined : data.nativeVideo}
                          camera={camera}
                          events={events}
                          now={now}
                          size="thumb"
                          selected={camera.id === selected}
                          onOpen={() => selectCamera(camera.id)}
                        />
                      </div>
                    ))}
                  </div>
                </section>
              ) : (
                <section className="cm-wall" aria-labelledby="wall-heading">
                  <header>
                    <h2 id="wall-heading">Cameras</h2>
                    <button type="button" className="cm-link" onClick={() => setMode('all')}>
                      {Math.min(4, ordered.length)} of {ordered.length} · Show all
                    </button>
                  </header>
                  <div className="cm-grid4">
                    {ordered.slice(0, 4).map((camera) => (
                      <CameraTile
                        nativeVideo={modal || reviewEvent ? undefined : data.nativeVideo}
                        key={camera.id}
                        onRemove={canManage ? () => void removeCamera(camera) : undefined}
                        removing={removing.has(camera.id)}
                        camera={camera}
                        events={events}
                        now={now}
                        pinned={pinned.includes(camera.id)}
                        onOpen={() => selectCamera(camera.id)}
                      />
                    ))}
                    {!ordered.length && <p className="cm-muted">No cameras connected. <a href="/setup#cameras">Add camera</a></p>}
                  </div>
                </section>
              )}
              <ResponseClock event={focus} cameras={cameras} />
              {(active.length > 0 || queue.length > 0) && !reviewEvent && (
                <section className="cm-active" aria-label="Open incidents">
                  {[...queue, ...active].map((event) => (
                    <button key={event.id} type="button" className="cm-btn" onClick={() => openReview(event.id)}>
                      {incidentRef(event)} · {needsDecision(event) ? 'Review' : 'Response'}
                    </button>
                  ))}
                </section>
              )}
            </aside>
          </>
        ) : (
          <section className="cm-all" aria-labelledby="all-heading">
            <h2 id="all-heading" className="cm-sr-only">Security camera wall</h2>
            <div className="cm-grid-all" style={{ '--camera-columns': ordered.length <= 1 ? 1 : ordered.length <= 4 ? 2 : ordered.length <= 9 ? 3 : 4, '--camera-rows': Math.ceil(ordered.length / (ordered.length <= 1 ? 1 : ordered.length <= 4 ? 2 : ordered.length <= 9 ? 3 : 4)) || 1 } as CSSProperties}>
              {ordered.map((camera: WallCamera) => (
                <CameraTile
                  nativeVideo={modal || reviewEvent ? undefined : data.nativeVideo}
                  key={camera.id}
                  onRemove={canManage ? () => void removeCamera(camera) : undefined}
                  removing={removing.has(camera.id)}
                  camera={camera}
                  events={events}
                  now={now}
                  pinned={pinned.includes(camera.id)}
                  onOpen={() => selectCamera(camera.id)}
                />
              ))}
              {!ordered.length && <div className="cm-wall-empty"><h3>No cameras connected</h3><p>Add a camera, then scan its QR code with your phone.</p><a className="cm-btn" href="/setup#cameras">Add camera</a></div>}
            </div>
          </section>
        )}
      </main>

      {reviewEvent && (
        <ReviewWindow
          key={reviewEvent.id}
          event={reviewEvent}
          cameras={cameras}
          events={events}
          now={now}
          clips={data.clips}
          floors={floors}
          guards={guards}
          siteName={data.siteName}
          sample={sample}
          queue={queue.length}
          act={act(reviewEvent)}
          close={closeReview}
        />
      )}
      {modal === 'guards' && (
        <Modal title="Guard phones" close={() => setModal(null)}>
          <GuardRoster guards={guards} sample={sample} admin={admin} now={now} />
        </Modal>
      )}
      {modal && typeof modal === 'object' && <CameraFocus nativeVideo={data.nativeVideo} cameras={ordered} cameraId={modal.full} events={events} now={now} pinned={pinned}
        change={id => { setSelected(id); setModal({ full: id }) }} togglePin={togglePin}
        openMap={id => { setModal(null); setSelected(id); setSelectedGuard(null); setMode('map') }} close={() => setModal(null)} />}

    </div>
  )
}
