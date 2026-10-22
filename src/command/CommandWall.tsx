import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  ArrowLeft,
  ArrowsOut,
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
import type { Incident } from '../classroom/contracts'
import { ReviewTonePlayer } from '../services/ReviewTonePlayer'
import { CameraTile } from './CameraTile'
import { FloorMap } from './FloorMap'
import { ResponseClock } from './ResponseClock'
import { ReviewWindow } from './ReviewWindow'
import {
  focusIncident,
  formatClock,
  incidentRef,
  isActiveResponse,
  needsDecision,
  orderCameras,
  wallStats,
  type ReviewAction,
  type ReviewPayload,
  type WallCamera,
} from './model'
import { useOptionalSession } from '../auth/context'
import type { MapFloor, WallGuard } from './types'
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

function Modal({ title, close, children, wide }: { title: string; close: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = ref.current
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [])
  return (
    <dialog
      ref={ref}
      className={`cm-modal ${wide ? 'cm-modal--wide' : ''}`}
      aria-label={title}
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

function GuardRoster({ guards, floors, sample, admin }: { guards: WallGuard[]; floors: MapFloor[]; sample: boolean; admin: boolean }) {
  const floorName = (id: string | null) => floors.find((f) => f.id === id)?.name ?? 'No floor'
  return (
    <div className="cm-pairing">
      {!guards.length ? (
        <p className="cm-muted">No guards yet. {admin ? 'Invite them in Setup → Guards.' : 'Ask an admin to invite guards.'}</p>
      ) : (
        <ul>
          {guards.map((guard) => (
            <li key={guard.id}>
              <span className="cm-guard-id">{guard.id}</span>
              <span>
                {guard.name}
                <small className="cm-muted"> · {floorName(guard.floorId)}{guard.x == null ? ' · no post' : ''}</small>
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
          : 'Guards sign in at /guard on their own phones. Alerts ring while the app is open and arrive as notifications when it is installed.'}
      </p>
      {admin && !sample && (
        <a className="cm-btn cm-btn--dark" href="/setup#guards">
          Manage guards in Setup
        </a>
      )}
    </div>
  )
}

export default function CommandWall() {
  const sample = new URLSearchParams(location.search).get('demo') === '1'
  const data = useCommand(sample)
  const { cameras, events, guards, floors } = data
  const session = useOptionalSession()
  const admin = session?.me?.role === 'admin'
  const [floorChoice, setFloorChoice] = useState<string | null>(null)
  const now = useNow()
  const [mode, setMode] = useState<'map' | 'all'>('map')
  const [selected, setSelected] = useState<string | null>(null)
  const [pinned, setPinned] = useState<string[]>(readPins)
  const [reviewing, setReviewing] = useState<string | null>(null)
  const deferred = useRef(new Set<string>())
  const [modal, setModal] = useState<'guards' | { full: string } | null>(null)
  const [sound, setSound] = useState(false)
  const tone = useRef<ReviewTonePlayer | null>(null)
  const seen = useRef<Set<string> | null>(null)

  useEffect(() => {
    localStorage.setItem(PIN_KEY, JSON.stringify(pinned))
  }, [pinned])

  const queue = useMemo(
    () => events.filter(needsDecision).sort((a, b) => a.received_at - b.received_at),
    [events],
  )
  const active = useMemo(() => events.filter(isActiveResponse), [events])
  const reviewEvent = events.find((e) => e.id === reviewing) ?? null

  // Auto-open the oldest incident that still needs a decision.
  useEffect(() => {
    if (reviewing && events.some((e) => e.id === reviewing)) return
    const next = queue.find((e) => !deferred.current.has(e.id))
    setReviewing(next?.id ?? null)
  }, [queue, reviewing, events])

  // Tone for incidents that arrive while this screen is open.
  useEffect(() => {
    const ids = new Set(events.map((e) => e.id))
    if (seen.current && sound && events.some((e) => needsDecision(e) && !seen.current!.has(e.id)))
      void tone.current?.play('physical-conflict')
    seen.current = ids
  }, [events, sound])
  useEffect(() => () => tone.current?.dispose(), [])
  const toggleSound = async () => {
    if (sound) {
      setSound(false)
      tone.current?.stop()
      return
    }
    tone.current ??= new ReviewTonePlayer()
    setSound(await tone.current.prime())
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || document.querySelector('dialog[open]')) return
      if (mode === 'all') setMode('map')
      else setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mode])

  const ordered = useMemo(() => orderCameras(cameras, events, pinned, now), [cameras, events, pinned, now])
  const stats = wallStats(cameras, events, now)
  const focus = focusIncident(events, now)
  const selectedCamera = cameras.find((c) => c.id === selected) ?? null
  const focusFloorId = focus ? cameras.find((c) => c.id === focus.camera_id)?.floorId : null
  const activeFloor =
    floors.find((f) => f.id === (selectedCamera?.floorId ?? floorChoice ?? focusFloorId)) ?? floors[0] ?? null
  const unplaced = cameras.filter((c) => !c.slot).length
  const onShift = guards.filter((g) => g.status === 'available')
  const selectCamera = useCallback((id: string) => {
    setSelected((current) => (current === id ? null : id))
    setMode('map')
  }, [])
  const chooseFloor = (id: string) => {
    setFloorChoice(id)
    setSelected(null)
  }
  const act = useCallback(
    (event: Incident) => (action: ReviewAction, payload?: ReviewPayload) => data.review(event, action, payload),
    [data],
  )
  const closeReview = () => {
    if (reviewEvent && needsDecision(reviewEvent)) deferred.current.add(reviewEvent.id)
    setReviewing(null)
  }
  const openReview = (id: string) => {
    deferred.current.delete(id)
    setReviewing(id)
  }
  const togglePin = (id: string) =>
    setPinned((list) => (list.includes(id) ? list.filter((p) => p !== id) : [...list, id]))

  const connectionLabel = sample
    ? 'Sample workspace'
    : data.connection === 'connected'
      ? 'Live'
      : data.connection === 'connecting'
        ? 'Connecting…'
        : 'Disconnected'

  return (
    <div className="cm-app">
      <a className="cm-skip" href="#cm-main">
        Skip to cameras
      </a>
      <header className="cm-top">
        <a className="cm-brand" href={sample ? '/wall?demo=1' : '/wall'}>
          NIVRA
        </a>
        <span className="cm-site">
          {data.siteName}
          {activeFloor ? ` / ${activeFloor.name}` : ''}
        </span>
        <span className={`cm-pill ${!sample && data.connection !== 'connected' ? 'cm-pill--amber' : ''}`} role="status">
          {connectionLabel}
        </span>
        <div className="cm-top-actions">
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
          {session?.me && (
            <button
              type="button"
              className="cm-icon-btn"
              aria-label={`Sign out ${session.me.name ?? ''}`.trim()}
              title={`${session.me.name ?? session.me.email ?? 'Signed in'} · sign out`}
              onClick={() => void session.signOut()}
            >
              <SignOut aria-hidden />
            </button>
          )}
          <button
            type="button"
            className="cm-icon-btn"
            aria-label={sound ? 'Mute incident sound' : 'Turn on incident sound'}
            aria-pressed={sound}
            onClick={() => void toggleSound()}
          >
            {sound ? <SpeakerHigh aria-hidden /> : <SpeakerSlash aria-hidden />}
          </button>
          <time className="cm-clock-now">{formatClock(now)}</time>
        </div>
      </header>

      {sample && (
        <p className="cm-banner">
          <strong>Sample workspace.</strong> Generated mall imagery and illustrative records. No live detection. Open a guard tab from
          Guards to hear the phone ring.
        </p>
      )}
      {!sample && (data.connection !== 'connected' || data.error) && (
        <p className="cm-banner cm-banner--warn" role="alert">
          <WarningCircle aria-hidden /> {data.error || 'Connecting to the local NIVRA service.'} Feeds and incidents are unavailable until
          it reconnects.
        </p>
      )}
      {!sample && data.connection === 'connected' && !cameras.length && (
        <p className="cm-banner">
          No cameras yet. Add and pair phones from the <a href="/">camera dashboard</a>. Name a camera after a map spot (for example
          “Atrium East”) to place it there; otherwise it takes the next free spot.
        </p>
      )}

      <section className="cm-stats" aria-label="Today at a glance">
        <div>
          <span>Cameras live</span>
          <strong>
            {stats.live} / {stats.total}
          </strong>
          <small>{stats.offline ? `${stats.offline} offline` : 'All connected'}</small>
        </div>
        <div>
          <span>Detection → review</span>
          <strong>{stats.reviewSeconds == null ? '—' : `${stats.reviewSeconds.toFixed(1)} s`}</strong>
          <small>median today</small>
        </div>
        <div>
          <span>Reviews today</span>
          <strong>{stats.reviews}</strong>
          <small>
            {stats.confirmed} confirmed · {stats.falseAlarms} false alarm · {stats.open} open
          </small>
        </div>
        <div>
          <span>Guards on shift</span>
          <strong>{onShift.length}</strong>
          <small>
            {sample
              ? `${guards.length} on roster · sample`
              : `${guards.filter((g) => g.online).length} online · ${guards.filter((g) => g.push).length} with alerts on`}
          </small>
        </div>
        <div>
          <span>Analysis</span>
          <strong>{stats.fps == null ? '—' : `${stats.fps.toFixed(1)} fps`}</strong>
          <small>
            {data.runtime?.device
              ? `avg per camera · ${data.runtime.device === 'camera-device' ? 'on the phones' : `on this computer (${data.runtime.device.toUpperCase()})`}`
              : 'avg per camera'}
          </small>
        </div>
      </section>

      <main id="cm-main" className={`cm-main cm-main--${mode}`} inert={reviewEvent ? true : undefined}>
        {mode === 'map' ? (
          <>
            <section className="cm-map-panel" aria-labelledby="map-heading">
              <header>
                <h2 id="map-heading">{activeFloor?.name ?? 'Floor plan'}</h2>
                {floors.length > 1 && (
                  <div className="cm-floor-tabs" role="tablist" aria-label="Floors">
                    {floors.map((floor) => (
                      <button
                        key={floor.id}
                        type="button"
                        role="tab"
                        aria-selected={floor.id === activeFloor?.id}
                        className={floor.id === activeFloor?.id ? 'is-on' : ''}
                        onClick={() => chooseFloor(floor.id)}
                      >
                        {floor.name}
                        {events.some((e) => (needsDecision(e) || isActiveResponse(e)) && cameras.find((c) => c.id === e.camera_id)?.floorId === floor.id) && (
                          <i className="cm-floor-alert" aria-label="incident on this floor" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
                <ul className="cm-legend" aria-label="Map legend">
                  <li><i className="cm-key cm-key--camera" /> Camera</li>
                  <li><i className="cm-key cm-key--guard" /> {sample ? 'Guard (sample)' : 'Guard post'}</li>
                  <li><i className="cm-key cm-key--incident" /> Incident</li>
                  <li><i className="cm-key cm-key--exit" /> Exit</li>
                </ul>
              </header>
              <div className="cm-map-scroll">
                {activeFloor ? (
                <FloorMap
                  floor={activeFloor}
                  guards={guards}
                  cameras={cameras}
                  events={events}
                  selected={selected}
                  onSelect={selectCamera}
                  focus={focus && (needsDecision(focus) || isActiveResponse(focus)) ? focus : null}
                  label={`${activeFloor.name} map. Select a camera to see its view.`}
                />
                ) : (
                  <div className="cm-empty-map">
                    <strong>No floors yet</strong>
                    <span className="cm-muted">
                      {admin ? 'Add a floor and upload its plan in Setup to see cameras and guards on a map.' : 'An admin needs to add a floor plan in Setup.'}
                    </span>
                    {admin && (
                      <a className="cm-btn cm-btn--dark" href="/setup">
                        Open Setup
                      </a>
                    )}
                  </div>
                )}
              </div>
              <p className="cm-hint" aria-live="polite">
                {selectedCamera
                  ? `${selectedCamera.label} selected · Esc to close`
                  : unplaced
                    ? `Click a camera to see its view · ${unplaced} camera${unplaced === 1 ? '' : 's'} not placed on a map yet`
                    : 'Click a camera to see its view'}
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
                  <CameraTile camera={selectedCamera} events={events} now={now} size="hero" pinned={pinned.includes(selectedCamera.id)} />
                  <div className="cm-selected-foot">
                    <span className="cm-muted">
                      {selectedCamera.slot?.covers
                        ? `Covers: ${selectedCamera.slot.covers}`
                        : selectedCamera.slot
                          ? `${floors.find((f) => f.id === selectedCamera.floorId)?.name ?? ''}`
                          : 'Not placed on a map'}
                    </span>
                    <button type="button" className="cm-btn" aria-pressed={pinned.includes(selectedCamera.id)} onClick={() => togglePin(selectedCamera.id)}>
                      <PushPin aria-hidden /> {pinned.includes(selectedCamera.id) ? 'Unpin' : 'Pin to wall'}
                    </button>
                    <button type="button" className="cm-btn cm-btn--dark" onClick={() => setModal({ full: selectedCamera.id })}>
                      <ArrowsOut aria-hidden /> Open full view
                    </button>
                  </div>
                  <div className="cm-thumbs" role="list" aria-label="Wall cameras">
                    {ordered.slice(0, 4).map((camera) => (
                      <div role="listitem" key={camera.id}>
                        <CameraTile
                          camera={camera}
                          events={events}
                          now={now}
                          size="thumb"
                          selected={camera.id === selected}
                          onOpen={() => setSelected(camera.id)}
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
                      {Math.min(4, cameras.length)} of {cameras.length} · Show all
                    </button>
                  </header>
                  <div className="cm-grid4">
                    {ordered.slice(0, 4).map((camera) => (
                      <CameraTile
                        key={camera.id}
                        camera={camera}
                        events={events}
                        now={now}
                        pinned={pinned.includes(camera.id)}
                        onOpen={() => selectCamera(camera.id)}
                      />
                    ))}
                    {!cameras.length && <p className="cm-muted">Cameras appear here once paired.</p>}
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
            <header>
              <h2 id="all-heading">All cameras · {cameras.length}</h2>
              <span className="cm-muted">
                {stats.live} live · {stats.offline} offline
              </span>
              <button type="button" className="cm-btn" onClick={() => setMode('map')}>
                <ArrowLeft aria-hidden /> Back to map <kbd>Esc</kbd>
              </button>
            </header>
            <div className="cm-grid-all">
              {ordered.map((camera: WallCamera) => (
                <CameraTile
                  key={camera.id}
                  camera={camera}
                  events={events}
                  now={now}
                  pinned={pinned.includes(camera.id)}
                  onOpen={() => {
                    setSelected(camera.id)
                    setMode('map')
                  }}
                />
              ))}
              <div className="cm-mini">
                <h3>{activeFloor?.name ?? 'Floor plan'}</h3>
                {activeFloor && (
                  <FloorMap
                    floor={activeFloor}
                    guards={guards}
                    cameras={cameras}
                    events={events}
                    compact
                    onSelect={selectCamera}
                    label="Mini map. Select a camera to open it on the map."
                  />
                )}
                <p className="cm-muted">Click a camera to open it on the map</p>
              </div>
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
          <GuardRoster guards={guards} floors={floors} sample={sample} admin={admin} />
        </Modal>
      )}
      {modal && typeof modal === 'object' && (() => {
        const camera = cameras.find((c) => c.id === modal.full)
        return camera ? (
          <Modal title={`${camera.label} · ${camera.name}`} close={() => setModal(null)} wide>
            <CameraTile camera={camera} events={events} now={now} size="hero" />
          </Modal>
        ) : null
      })()}
    </div>
  )
}
