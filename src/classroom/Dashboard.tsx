import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import {
  VideoCamera,
  Flag,
  ChartBar,
  GearSix,
  Plus,
  CaretDown,
  ArrowUpRight,
  Buildings,
  MapPin,
  WifiSlash,
  X,
  Copy,
  Check,
  SpeakerHigh,
  SpeakerSlash,
  ShieldCheck,
  WarningCircle,
  DownloadSimple,
  PlugsConnected,
  MonitorPlay,
} from '@phosphor-icons/react'
import { api, type CameraLocation, type Incident } from './contracts'
import { useClassroom } from './useClassroom'
import { demoSnapshot } from './demo'
import { ReviewTonePlayer } from '../services/ReviewTonePlayer'
import './classroom.css'
import { TrackOverlay } from './TrackOverlay'
import { PairingCode } from './PairingCode'
import { isLocalDashboard } from './contracts'

type Section = 'Live' | 'Incidents' | 'Cameras' | 'Analytics' | 'Settings'
type Modal =
  | { type: 'camera'; camera?: CameraLocation }
  | { type: 'details'; camera: CameraLocation }
  | { type: 'pair'; camera: CameraLocation; url: string; remoteReady: boolean; expiresAt: number }
  | { type: 'operator'; url: string }
  | null
const navigation = [
  { name: 'Live', icon: MonitorPlay },
  { name: 'Incidents', icon: Flag },
  { name: 'Cameras', icon: VideoCamera },
  { name: 'Analytics', icon: ChartBar },
  { name: 'Settings', icon: GearSix },
] as const
const timeLabel = (time: number) =>
  new Date(time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const coverageLabel = (camera: CameraLocation) =>
  camera.error
    ? 'Analysis error'
    : camera.feed !== 'live'
      ? 'No live analysis'
      : camera.analysis !== 'current'
        ? 'Analysis waiting'
        : camera.result?.conflict?.status === 'warming'
          ? 'Collecting video'
          : camera.result?.coverage?.status === 'limited'
            ? 'Limited coverage'
            : 'Analysis current'

function ModalFrame({
  title,
  children,
  close,
}: {
  title: string
  children: ReactNode
  close: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    element?.querySelector<HTMLInputElement>('[data-initial-focus]')?.focus()
    return () => element?.close()
  }, [])
  return (
    <dialog
      ref={dialog}
      className="nv-modal"
      aria-labelledby="modal-heading"
      onCancel={(event) => {
        event.preventDefault()
        close()
      }}
    >
      <header>
        <h2 id="modal-heading">{title}</h2>
        <button
          className="nv-icon-button"
          aria-label="Close dialog"
          onClick={close}
        >
          <X size={22} />
        </button>
      </header>
      {children}
    </dialog>
  )
}

export default function Dashboard() {
  const demo = new URLSearchParams(location.search).get('demo') === '1'
  const live = useClassroom(!demo),
    [sample, setSample] = useState(demoSnapshot)
  const data = demo ? sample : live.snapshot
  const connected = demo || live.connection === 'connected'
  const [section, setSection] = useState<Section>('Live'),
    [floor, setFloor] = useState('all'),
    [selected, setSelected] = useState('')
  const [search, setSearch] = useState(''),
    [layout, setLayout] = useState<'grid' | 'focus'>('grid')
  const [modal, setModal] = useState<Modal>(null),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [copied, setCopied] = useState(false)
  const [eventFilter, setEventFilter] = useState('all'),
    [overlays, setOverlays] = useState(true),
    [sound, setSound] = useState(false)
  const tone = useRef<ReviewTonePlayer | null>(null),
    seen = useRef<Set<string> | null>(null),
    lastTone = useRef(-Infinity)
  const cameras = data?.cameras || [],
    events = data?.events || [],
    pending = events.filter((e) => e.status === 'open')
  const floors = [...new Set(cameras.map((c) => `${c.building} / ${c.floor}`))]
  const visible = cameras.filter(
    (c) =>
      (floor === 'all' || `${c.building} / ${c.floor}` === floor) &&
      `${c.name} ${c.building} ${c.floor}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  )
  const online = connected ? cameras.filter((c) => c.feed === 'live').length : 0
  const gaps = connected
    ? cameras.filter(
        (c) =>
          c.feed !== 'live' ||
          c.analysis !== 'current' ||
          c.result?.coverage?.status === 'limited',
      ).length
    : cameras.length
  useEffect(() => {
    if (!data) return
    const current = new Set(data.events.map((e) => e.id))
    if (
      seen.current &&
      sound &&
      data.events.some(
        (e) => e.status === 'open' && !seen.current!.has(e.id),
      ) &&
      Date.now() - lastTone.current > 10000
    ) {
      lastTone.current = Date.now()
      void tone.current?.play('physical-conflict')
    }
    seen.current = current
  }, [data, sound])
  useEffect(
    () => () => {
      tone.current?.dispose()
    },
    [],
  )
  const toggleSound = async () => {
    if (sound) {
      setSound(false)
      tone.current?.stop()
      return
    }
    tone.current ||= new ReviewTonePlayer()
    if (await tone.current.prime()) setSound(true)
    else
      setNotice('Your browser blocked alert audio. Use the visual event desk.')
  }
  const focusCamera = (id: string) => {
    setSection('Live')
    setFloor('all')
    setSearch('')
    setSelected(id)
    window.setTimeout(
      () =>
        document
          .getElementById(`camera-${id}`)
          ?.scrollIntoView({ block: 'center', behavior: 'smooth' }),
      60,
    )
  }
  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setNotice('')
    try {
      await action()
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : 'Action could not be completed.',
      )
    } finally {
      setBusy(false)
    }
  }
  const transition = (event: Incident, status: 'acknowledged' | 'resolved') =>
    void run(async () => {
      if (demo) {
        setSample((old) => ({
          ...old,
          events: old.events.map((e) =>
            e.id === event.id
              ? {
                  ...e,
                  status,
                  revision: e.revision + 1,
                  updated_at: Date.now(),
                }
              : e,
          ),
          analytics: {
            ...old.analytics,
            pending: old.analytics.pending - (event.status === 'open' ? 1 : 0),
            resolved: old.analytics.resolved + (status === 'resolved' ? 1 : 0),
          },
        }))
      } else
        await api(`/events/${event.id}`, 'PATCH', {
          status,
          revision: event.revision,
        })
    })
  const pair = (camera: CameraLocation) =>
    void run(async () => {
      if (demo) {
        setNotice(
          'Sample view cannot pair devices. Open the live dashboard to add your cameras.',
        )
        setModal(null)
        return
      }
      const result = await api<{ url: string; remoteReady: boolean }>(
        `/cameras/${camera.id}/pair`,
        'POST',
      )
      setCopied(false)
      setModal({ type: 'pair', camera, ...result, expiresAt: Date.now() + 300000 })
    })
  const saveCamera = (
    event: FormEvent<HTMLFormElement>,
    camera?: CameraLocation,
  ) => {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    void run(async () => {
      if (demo) {
        setNotice(
          'Camera changes are disabled in sample view. Open the live dashboard.',
        )
        return
      }
      await api(
        camera ? `/cameras/${camera.id}` : '/cameras',
        camera ? 'PATCH' : 'POST',
        {
          name: fields.get('name'),
          building: fields.get('building'),
          floor: fields.get('floor'),
          enabled: camera?.enabled ?? true,
        },
      )
      setModal(null)
    })
  }
  const toggleCamera = (camera: CameraLocation) =>
    void run(async () => {
      if (demo) {
        setNotice('Sample camera controls do not affect real cameras.')
        return
      }
      await api(`/cameras/${camera.id}`, 'PATCH', {
        name: camera.name,
        building: camera.building,
        floor: camera.floor,
        enabled: !camera.enabled,
      })
      setModal(null)
    })
  const exportEvents = () => {
    const columns = [
      'id',
      'camera_name',
      'location',
      'received_at',
      'status',
      'model',
    ] as const
    const cell = (value: unknown) =>
      '"' +
      String(value)
        .replace(/^[=+@-]/, "'$&")
        .replaceAll('"', '""') +
      '"'
    const csv = [
      columns.join(','),
      ...events.map((event) =>
        columns
          .map((key) =>
            cell(
              key === 'received_at'
                ? new Date(event[key]).toISOString()
                : event[key],
            ),
          )
          .join(','),
      ),
    ].join('\r\n')
    const url = URL.createObjectURL(
        new Blob([csv], { type: 'text/csv;charset=utf-8' }),
      ),
      link = document.createElement('a')
    link.href = url
    link.download = demo ? 'nivra-sample-events.csv' : 'nivra-event-records.csv'
    link.click()
    URL.revokeObjectURL(url)
  }
  return (
    <div className="nv-app">
      <a className="nv-skip" href="#main-content">
        Skip to cameras
      </a>
      <header className="nv-header">
        <a
          className="nv-brand"
          href={demo ? '/?demo=1' : '/'}
          aria-label="Nivra dashboard"
        >
          <img src="/brand/nivra-mark.png" alt="" />
          <strong>NIVRA</strong>
        </a>
        <span className="nv-operator">SCHOOL OPERATOR</span>
        <div className="nv-header-right">
          <span className={`nv-service ${!connected ? 'nv-amber' : ''}`}>
            <span className="nv-dot" />
            {demo
              ? 'SAMPLE WORKSPACE'
              : connected
                ? 'LOCAL SERVICE CONNECTED'
                : 'SERVICE DISCONNECTED'}
          </span>
          <button
            className="nv-icon-button"
            aria-label={
              sound ? 'Mute review alerts' : 'Enable review alert sound'
            }
            onClick={() => void toggleSound()}
          >
            {sound ? <SpeakerHigh size={21} /> : <SpeakerSlash size={21} />}
          </button>
          <span className="nv-avatar" aria-label="Local operator">
            OP
          </span>
        </div>
      </header>
      <nav className="nv-rail" aria-label="Main navigation">
        {navigation.map(({ name, icon: Icon }) => (
          <button
            key={name}
            className={section === name ? 'is-active' : ''}
            aria-current={section === name ? 'page' : undefined}
            onClick={() => setSection(name)}
          >
            <Icon size={23} weight={section === name ? 'fill' : 'regular'} />
            <span>{name}</span>
            {name === 'Incidents' && pending.length > 0 && (
              <b className="nv-nav-count">{pending.length}</b>
            )}
          </button>
        ))}
        <a href="/lab" className="nv-lab-link">
          <PlugsConnected size={22} />
          <span>Vision lab</span>
        </a>
      </nav>
      <aside className="nv-directory" aria-label="Camera locations">
        <div className="nv-directory-heading">
          <span>LOCATIONS</span>
          <span>{cameras.length.toString().padStart(2, '0')}</span>
        </div>
        {!cameras.length && (
          <p className="nv-muted nv-location-empty">
            Your classrooms will appear here.
          </p>
        )}
        {[...new Set(cameras.map((c) => c.building))].map((building) => (
          <div key={building} className="nv-building">
            <h2>
              <Buildings size={18} />
              {building}
              <CaretDown size={13} />
            </h2>
            {[
              ...new Set(
                cameras
                  .filter((c) => c.building === building)
                  .map((c) => c.floor),
              ),
            ].map((floorName) => (
              <section key={floorName}>
                <h3>{floorName}</h3>
                {cameras
                  .filter(
                    (c) => c.building === building && c.floor === floorName,
                  )
                  .map((camera) => {
                    const attention = events.some(
                      (e) => e.camera_id === camera.id && e.status === 'open',
                    )
                    return (
                      <button
                        className={`nv-location ${selected === camera.id ? 'is-selected' : ''}`}
                        key={camera.id}
                        onClick={() => focusCamera(camera.id)}
                      >
                        <span>{camera.name}</span>
                        <small>
                          <span
                            className={`nv-dot ${attention ? 'nv-amber' : !connected || camera.feed !== 'live' ? 'nv-gray' : ''}`}
                          />
                          {attention
                            ? 'Review needed'
                            : !connected
                              ? 'Disconnected'
                              : camera.feed === 'live'
                                ? camera.result?.coverage?.status === 'limited'
                                  ? 'Limited coverage'
                                  : 'Online'
                                : camera.feed === 'paused'
                                  ? 'Paused'
                                  : 'Offline'}
                        </small>
                      </button>
                    )
                  })}
              </section>
            ))}
          </div>
        ))}
        <div className="nv-directory-bottom">
          <ShieldCheck size={20} />
          <div>
            <strong>Video stays transient</strong>
            <span>Event records only</span>
          </div>
        </div>
      </aside>
      <main id="main-content" className="nv-main">
        <div className="nv-breadcrumb">
          Campus <span>/</span> Classrooms
        </div>
        <div className={`nv-notice ${demo ? 'nv-demo-notice' : ''}`}>
          {demo ? (
            <>
              <strong>Sample view</strong>
              <span>
                Generated imagery & illustrative events. No live detection.
              </span>
              <a href="/">
                Open live dashboard <ArrowUpRight />
              </a>
            </>
          ) : (
            <>
              <span className="nv-dot nv-amber" />
              <span>
                <strong>Experimental classroom pilot.</strong> Accuracy for
                30–50 people is not yet validated.
              </span>
              <button
                className="nv-text-button"
                onClick={() => setSection('Settings')}
              >
                View setup <ArrowUpRight />
              </button>
            </>
          )}
        </div>
        {(!connected || live.error) && !demo && (
          <div role="alert" className="nv-notice nv-warning">
            <WarningCircle size={19} />
            <span>
              {live.error || 'Connecting to the local service.'} Feeds and
              analysis are unavailable until reconnected.
            </span>
            <a href="/lab">Browser lab</a>
          </div>
        )}
        {connected && !demo && data?.service !== 'ready' && (
          <div role="status" className="nv-notice nv-warning">
            <WarningCircle size={19} />
            <span>
              {data?.service === 'error'
                ? 'Local models could not start. Video can stream, but analysis is unavailable.'
                : 'Loading local models. Analysis will begin when they are ready.'}
            </span>
          </div>
        )}
        {notice && (
          <div role="status" className="nv-notice nv-warning">
            <span>{notice}</span>
            <button
              className="nv-icon-button"
              aria-label="Dismiss message"
              onClick={() => setNotice('')}
            >
              <X />
            </button>
          </div>
        )}
        <div className="nv-page-heading">
          <div>
            <h1>{section === 'Live' ? 'Live view' : section}</h1>
          </div>
          <div className="nv-heading-actions">
            {section === 'Live' && (
              <label>
                <span className="nv-sr-only">Search cameras</span>
                <input
                  className="nv-search"
                  placeholder="Search cameras…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
            )}
            {(section === 'Live' || section === 'Cameras') && (
              <button
                className="nv-primary"
                disabled={busy || (!connected && !demo) || cameras.length >= 4}
                onClick={() => setModal({ type: 'camera' })}
              >
                <Plus size={17} />
                Add camera
              </button>
            )}
            {section === 'Incidents' && (
              <button
                className="nv-secondary"
                onClick={exportEvents}
                disabled={!events.length}
              >
                <DownloadSimple />
                Export shown records
              </button>
            )}
          </div>
        </div>
        {section === 'Live' && (
          <div className="nv-live-toolbar">
            <span>
              <strong>{cameras.length} cameras</strong> · {online} connected ·{' '}
              {cameras.length - online} offline
            </span>
            <span>
              Analysis:{' '}
              {connected
                ? cameras.filter((c) => c.analysis === 'current').length
                : 0}{' '}
              current
            </span>
            <label>
              <span className="nv-sr-only">Filter locations</span>
              <select
                value={floor}
                onChange={(event) => setFloor(event.target.value)}
              >
                <option value="all">All floors</option>
                {floors.map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
            </label>
            <div className="nv-layout-switch" aria-label="Camera layout">
              <button
                aria-pressed={layout === 'grid'}
                onClick={() => setLayout('grid')}
              >
                2 × 2
              </button>
              <button
                aria-pressed={layout === 'focus'}
                onClick={() => setLayout('focus')}
              >
                Focus
              </button>
            </div>
          </div>
        )}
        {section === 'Live' && (
          <div
            className={`nv-feeds ${layout === 'focus' ? 'nv-focus-layout' : ''}`}
          >
            {visible.map((camera) => {
              const attention = events.some(
                  (e) => e.camera_id === camera.id && e.status === 'open',
                ),
                preview = live.previews[camera.id]
              const fresh =
                connected &&
                camera.feed === 'live' &&
                (demo ||
                  Boolean(
                    preview &&
                      preview.generation === camera.generation &&
                      Date.now() - preview.received < 6000,
                  ))
              const image = demo ? '/demo/classroom-sample.png' : preview?.url
              return (
                <article
                  id={`camera-${camera.id}`}
                  className={`nv-camera-card ${attention ? 'needs-review' : ''} ${selected === camera.id ? 'is-focused' : ''}`}
                  key={camera.id}
                  aria-label={camera.name}
                >
                  <header className="nv-card-header">
                    <div>
                      <h2>{camera.name}</h2>
                      <p>
                        {camera.building} · {camera.floor}
                      </p>
                    </div>
                    <span className={attention ? 'nv-camera-badge' : ''}>
                      <span
                        className={`nv-dot ${attention ? 'nv-amber' : !fresh ? 'nv-gray' : ''}`}
                      />
                      {attention
                        ? 'Review needed'
                        : fresh
                          ? demo
                            ? 'Sample'
                            : 'Live'
                          : 'Offline'}
                    </span>
                    <button
                      className="nv-icon-button"
                      aria-label={`Details for ${camera.name}`}
                      onClick={() => setModal({ type: 'details', camera })}
                    >
                      <GearSix size={17} />
                    </button>
                  </header>
                  <div
                    className="nv-camera-image"
                    style={
                      !demo && preview
                        ? { aspectRatio: `${preview.width}/${preview.height}` }
                        : undefined
                    }
                  >
                    {fresh && image ? (
                      <img
                        src={image}
                        alt={
                          demo
                            ? 'Generated sample classroom; not a live camera'
                            : `Live view of ${camera.name}`
                        }
                      />
                    ) : (
                      <div className="nv-feed-empty">
                        <WifiSlash size={34} />
                        <strong>
                          {camera.feed === 'paused'
                            ? 'Camera paused'
                            : !connected
                              ? 'Service disconnected'
                              : camera.feed === 'live'
                                ? 'Waiting for preview'
                                : 'Camera offline'}
                        </strong>
                        <span>
                          {camera.feed === 'paused'
                            ? 'Enable this camera to reconnect.'
                            : 'Pair a device to see this classroom.'}
                        </span>
                        {connected && camera.enabled && !demo && (
                          <button
                            className="nv-feed-connect"
                            onClick={() => pair(camera)}
                          >
                            Connect device <ArrowUpRight />
                          </button>
                        )}
                      </div>
                    )}
                    <div className="nv-camera-top">
                      <span className="nv-video-label">
                        {demo ? 'SAMPLE VIEW' : fresh ? 'LIVE' : 'NO LIVE FEED'}
                      </span>
                      {attention && (
                        <span className="nv-review-label">
                          <Flag size={13} weight="fill" />
                          Review needed
                        </span>
                      )}
                    </div>
                    {fresh &&
                      !demo &&
                      overlays &&
                      preview &&
                      Math.abs(
                        preview.timestampMs - (camera.result?.timestampMs ?? 0),
                      ) < 700 &&
                      camera.analysis === 'current' && (
                        <TrackOverlay
                          tracks={camera.result?.tracks}
                          width={preview.width}
                          height={preview.height}
                        />
                      )}
                    {fresh && (
                      <span className="nv-image-caption">
                        {demo
                          ? 'Generated image · not analyzed'
                          : camera.result?.coverage
                            ? `${camera.result.coverage.observedPeople} people tracked · ${camera.result.coverage.actionPeople} in latest action view`
                            : 'Waiting for analysis'}
                      </span>
                    )}
                  </div>
                  <div className="nv-card-footer">
                    <span
                      className={
                        !fresh || camera.result?.coverage?.status === 'limited'
                          ? 'nv-amber-text'
                          : ''
                      }
                    >
                      {fresh ? (
                        <ShieldCheck size={15} />
                      ) : (
                        <WarningCircle size={15} />
                      )}{' '}
                      {connected
                        ? coverageLabel(camera)
                        : 'Analysis unavailable'}
                    </span>
                    <button
                      className="nv-text-button"
                      onClick={() => setModal({ type: 'details', camera })}
                    >
                      Details <ArrowUpRight size={15} />
                    </button>
                  </div>
                </article>
              )
            })}
            {!visible.length && (
              <section className="nv-empty">
                <VideoCamera size={44} weight="light" />
                <h2>Your first classroom starts here.</h2>
                <p>
                  Add a location, pair a phone or laptop, and keep its camera
                  page open. Up to four locations in this pilot.
                </p>
                <button
                  className="nv-primary"
                  disabled={!connected}
                  onClick={() => setModal({ type: 'camera' })}
                >
                  <Plus />
                  Add your first camera
                </button>
                <a href="/?demo=1">
                  Explore the sample workspace <ArrowUpRight />
                </a>
              </section>
            )}
          </div>
        )}
        {section === 'Cameras' && (
          <section className="nv-content-panel">
            <h2>
              Connected locations{' '}
              <span className="nv-muted">{cameras.length} / 4</span>
            </h2>
            <p className="nv-muted">
              Give each camera a clear classroom and floor. Pairing a new device
              revokes the previous device.
            </p>
            {cameras.map((camera) => (
              <div className="nv-camera-row" key={camera.id}>
                <VideoCamera size={24} />
                <div>
                  <strong>{camera.name}</strong>
                  <span>
                    {camera.building} · {camera.floor}
                  </span>
                </div>
                <span className="nv-small-status">
                  {connected ? camera.feed : 'disconnected'}
                </span>
                <button
                  className="nv-secondary"
                  onClick={() => setModal({ type: 'camera', camera })}
                >
                  Edit
                </button>
                <button
                  className="nv-primary"
                  disabled={!camera.enabled || !connected || busy}
                  onClick={() => pair(camera)}
                >
                  Pair device
                </button>
              </div>
            ))}
            {!cameras.length && (
              <p>No locations yet. Add your first camera above.</p>
            )}
          </section>
        )}
        {section === 'Incidents' && (
          <section className="nv-content-panel">
            <div className="nv-panel-heading">
              <h2>Review history</h2>
              <label>
                <span className="nv-sr-only">Filter event status</span>
                <select
                  value={eventFilter}
                  onChange={(event) => setEventFilter(event.target.value)}
                >
                  <option value="all">All statuses</option>
                  <option value="open">Needs review</option>
                  <option value="acknowledged">Acknowledged</option>
                  <option value="resolved">Resolved</option>
                </select>
              </label>
            </div>
            <p className="nv-muted">
              Latest 500 event records at most. No recorded video is available
              for playback.
            </p>
            {events
              .filter((e) => eventFilter === 'all' || e.status === eventFilter)
              .map((event) => (
                <div className="nv-history-item" key={event.id}>
                  <div>
                    <span className="nv-eyebrow">
                      {new Date(event.received_at).toLocaleDateString()} ·{' '}
                      {timeLabel(event.received_at)}
                    </span>
                    <h3>{event.camera_name}</h3>
                    <p>Possible physical conflict · {event.status}</p>
                    <small>{event.location}</small>
                  </div>
                  <div className="nv-actions">
                    <button
                      className="nv-secondary"
                      onClick={() => focusCamera(event.camera_id)}
                    >
                      Open live view
                    </button>
                    {event.status !== 'resolved' && (
                      <button
                        className="nv-primary"
                        disabled={busy || !connected}
                        onClick={() =>
                          transition(
                            event,
                            event.status === 'open'
                              ? 'acknowledged'
                              : 'resolved',
                          )
                        }
                      >
                        {event.status === 'open' ? 'Acknowledge' : 'Resolve'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            {!events.some(
              (e) => eventFilter === 'all' || e.status === eventFilter,
            ) && (
              <div className="nv-inline-empty">
                <Flag size={30} />
                <h3>No events in this view</h3>
                <p>No alerts does not establish that the classroom is safe.</p>
              </div>
            )}
          </section>
        )}
        {section === 'Analytics' && (
          <>
            <div className="nv-metrics">
              {[
                ['Review events', data?.analytics.total || 0],
                ['Pending review', data?.analytics.pending || 0],
                ['Resolved', data?.analytics.resolved || 0],
              ].map(([label, value]) => (
                <section key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                  <small>
                    {demo
                      ? 'Illustrative records'
                      : 'All locally stored records'}
                  </small>
                </section>
              ))}
            </div>
            <section className="nv-content-panel">
              <h2>Current camera coverage</h2>
              <p className="nv-muted">
                Live operating state. These counts are not model accuracy
                measurements.
              </p>
              {cameras.map((camera) => (
                <div key={camera.id} className="nv-coverage-row">
                  <div>
                    <strong>{camera.name}</strong>
                    <small>
                      {connected
                        ? coverageLabel(camera)
                        : 'Service disconnected'}
                    </small>
                  </div>
                  <div>
                    <span>
                      {camera.result?.coverage?.analyzedPeople ?? '—'} people
                      analyzed
                    </span>
                    <small>
                      {camera.framesAnalyzed} frames analyzed /{' '}
                      {camera.framesReceived} received · {camera.framesReplaced}{' '}
                      replaced
                    </small>
                  </div>
                </div>
              ))}
            </section>
            <div className="nv-notice">
              <WarningCircle />
              <span>
                Classroom recall, false-alert rate and alert delay still require
                representative labelled footage. No accuracy percentage is
                available.
              </span>
            </div>
          </>
        )}
        {section === 'Settings' && (
          <section className="nv-content-panel nv-settings">
            <h2>Operator preferences</h2>
            <label className="nv-setting-row">
              <span>
                <strong>Visible person tracks</strong>
                <small>
                  Show current observed boxes. Ambiguous tracks are dashed.
                </small>
              </span>
              <input
                type="checkbox"
                checked={overlays}
                onChange={(event) => setOverlays(event.target.checked)}
              />
            </label>
            <label className="nv-setting-row">
              <span>
                <strong>Audible review alerts</strong>
                <small>New events only, at most once every ten seconds.</small>
              </span>
              <input
                type="checkbox"
                checked={sound}
                onChange={() => void toggleSound()}
              />
            </label>
            <h2>Analysis & connection</h2>
            <dl>
              <dt>Backend</dt>
              <dd>Local experimental AI · {data?.service || 'unavailable'}</dd>
              <dt>Person model</dt>
              <dd>{data?.runtime?.personModel || 'Unavailable'}</dd>
              <dt>Fight candidate</dt>
              <dd>{data?.runtime?.fightModel || 'Unavailable'}</dd>
              <dt>Remote phone access</dt>
              <dd>
                {data?.publicOrigin
                  ? `${data.publicOrigin} · public bridge configured`
                  : 'Not configured · HTTPS endpoint required'}
              </dd>
              <dt>Retention</dt>
              <dd>Live frames in memory; event records on this computer</dd>
            </dl>
            <p>
              The desktop must remain running. Camera pages must stay in the
              foreground. Crowds, occlusion, lighting and network delays can
              leave gaps in coverage.
            </p>
            <p>
              Remote cameras use an encrypted relay to this PC. Frames are not
              recorded. The public bridge and this PC must stay running.
            </p>
            {!demo && isLocalDashboard && data?.publicOrigin && <button className="nv-primary" onClick={() => void run(async () => {
              const result = await api<{url: string}>('/operator/invite', 'POST')
              setModal({ type: 'operator', url: result.url })
            })}>Open public dashboard <ArrowUpRight /></button>}
            {!isLocalDashboard && <button className="nv-secondary" onClick={() => void api('/operator/logout', 'POST').then(() => location.reload()).catch(() => setNotice('Could not sign out. Try again.'))}>Sign out</button>}
            <a className="nv-secondary" href="/lab">
              Open single-camera / browser lab <ArrowUpRight />
            </a>
            <a className="nv-text-button" href={demo ? '/' : '/?demo=1'}>
              {demo ? 'Return to live dashboard' : 'Explore sample workspace'}{' '}
              <ArrowUpRight />
            </a>
          </section>
        )}
      </main>
      <aside className="nv-event-desk" aria-label="Review queue">
        <div className="nv-event-desk-heading">
          <h2>
            Review queue <span className="nv-count">{pending.length}</span>
          </h2>
          <button
            className="nv-icon-button"
            aria-label="Open event history"
            onClick={() => setSection('Incidents')}
          >
            <ArrowUpRight size={21} />
          </button>
        </div>
        {events
          .filter((e) => e.status === 'open')
          .slice(0, 4)
          .map((event) => (
            <article className="nv-review-event" key={event.id}>
              <div className="nv-event-meta">
                <span>
                  <span className="nv-dot nv-amber" />
                  NEEDS REVIEW
                </span>
                <time>{timeLabel(event.received_at)}</time>
              </div>
              <h3>{event.camera_name}</h3>
              <p className="nv-event-location">
                <MapPin size={14} />
                {event.location}
              </p>
              <h4>Possible physical conflict</h4>
              <p>{event.detail}</p>
              <button
                className="nv-primary"
                onClick={() => focusCamera(event.camera_id)}
              >
                Open live view <ArrowUpRight size={17} />
              </button>
              <button
                className="nv-secondary"
                disabled={busy || !connected}
                onClick={() => transition(event, 'acknowledged')}
              >
                Acknowledge
              </button>
              <small>Human review required · no video saved</small>
            </article>
          ))}
        {!pending.length && (
          <div className="nv-quiet">
            <ShieldCheck size={32} weight="light" />
            <h3>No pending reviews</h3>
            <p>
              {!online
                ? 'Connect a camera to begin monitoring.'
                : 'New review events will appear here.'}
            </p>
          </div>
        )}
        <section className="nv-location-context">
          <h2>Locations</h2>
          <p>Classroom directory</p>
          {cameras.map((camera) => (
            <button
              key={camera.id}
              onClick={() => focusCamera(camera.id)}
              className={selected === camera.id ? 'is-selected' : ''}
            >
              <MapPin size={18} />
              <span>
                <strong>{camera.name}</strong>
                <small>
                  {camera.building} · {camera.floor}
                </small>
              </span>
              <ArrowUpRight size={15} />
            </button>
          ))}
          {!cameras.length && (
            <p>Add a camera to place your classrooms here.</p>
          )}
        </section>
        <div className="nv-recent-heading">
          <span>Recent activity</span>
          <button
            className="nv-text-button"
            onClick={() => setSection('Incidents')}
          >
            View all
          </button>
        </div>
        {events
          .filter((e) => e.status !== 'open')
          .slice(0, 4)
          .map((event) => (
            <article className="nv-recent-event" key={event.id}>
              <span className="nv-recent-icon">
                <Check size={17} />
              </span>
              <div>
                <strong>{event.camera_name}</strong>
                <p>
                  {event.status === 'resolved'
                    ? 'Review resolved'
                    : 'Review acknowledged'}
                </p>
                <small>{timeLabel(event.received_at)} · Event record</small>
                {event.status === 'acknowledged' && (
                  <button
                    className="nv-text-button"
                    disabled={busy || !connected}
                    onClick={() => transition(event, 'resolved')}
                  >
                    Mark resolved
                  </button>
                )}
              </div>
            </article>
          ))}
        {!events.length && (
          <p className="nv-muted nv-no-activity">No event records yet.</p>
        )}
        <div className="nv-event-footnote">
          <ShieldCheck size={19} />
          <p>
            Review the scene before responding. An alert is a signal to check,
            not a verdict.
          </p>
        </div>
      </aside>
      <footer className="nv-statusbar">
        <span>
          <span className={`nv-dot ${!online ? 'nv-gray' : ''}`} />
          {online} of {cameras.length} cameras{' '}
          {demo ? 'shown online' : 'online'}
        </span>
        <span>
          <WarningCircle size={14} />
          {gaps} coverage gaps
        </span>
        <span>
          <ShieldCheck size={14} />
          No video recorded
        </span>
        <span className="nv-statusbar-right">
          {demo ? 'DEMONSTRATION ONLY' : 'LOCAL ANALYSIS · EXPERIMENTAL'}
        </span>
      </footer>
      {modal?.type === 'camera' && (
        <ModalFrame
          title={
            modal.camera ? 'Edit camera location' : 'Add a camera location'
          }
          close={() => setModal(null)}
        >
          <form onSubmit={(event) => saveCamera(event, modal.camera)}>
            <p className="nv-muted">
              Start with a clear location. You can pair its device after saving.
            </p>
            <label>
              Classroom name
              <input
                name="name"
                data-initial-focus
                maxLength={50}
                required
                defaultValue={modal.camera?.name || ''}
                placeholder="Classroom 8A"
                autoFocus
              />
            </label>
            <label>
              Building
              <input
                name="building"
                maxLength={70}
                required
                defaultValue={modal.camera?.building || 'Main building'}
              />
            </label>
            <label>
              Floor
              <input
                name="floor"
                maxLength={40}
                required
                defaultValue={modal.camera?.floor || 'Floor 1'}
              />
            </label>
            <button className="nv-primary" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Save location'}
            </button>
            {notice && <p role="alert">{notice}</p>}
          </form>
        </ModalFrame>
      )}
      {modal?.type === 'operator' && <ModalFrame title="Your private dashboard link" close={() => setModal(null)}>
        <p>This link unlocks camera feeds and incident records. Keep it private. It works once within five minutes.</p>
        <a className="nv-primary" href={modal.url} target="_blank" rel="noreferrer">Open public dashboard <ArrowUpRight /></a>
      </ModalFrame>}
      {modal?.type === 'pair' && (
        <ModalFrame
          title={`Connect ${modal.camera.name}`}
          close={() => setModal(null)}
        >
          <p>
            Scan the QR code with your phone’s Camera app, or open the link on
            another laptop. It grants access to this camera only.
          </p>
          <PairingCode url={modal.url} expiresAt={modal.expiresAt} remoteReady={modal.remoteReady} renew={() => pair(modal.camera)} />
          {!modal.remoteReady && (
            <p className="nv-notice nv-warning">
              This link works on this computer only. Remote phones need an HTTPS
              endpoint configured first.
            </p>
          )}
          <label>
            Pairing link
            <input
              readOnly
              value={modal.url}
              onFocus={(event) => event.target.select()}
            />
          </label>
          <div className="nv-actions">
            <button
              className="nv-primary"
              onClick={() =>
                void navigator.clipboard
                  .writeText(modal.url)
                  .then(() => setCopied(true))
                  .catch(() => setNotice('Copy the selected link manually.'))
              }
            >
              {copied ? <Check /> : <Copy />}
              {copied ? 'Copied' : 'Copy link'}
            </button>
            <a
              className="nv-secondary"
              href={modal.url}
              target="_blank"
              rel="noreferrer"
            >
              Use this device <ArrowUpRight />
            </a>
          </div>
          <p className="nv-muted">
            Pairing revokes the previous device. No audio or video recordings
            are created.
          </p>
        </ModalFrame>
      )}
      {modal?.type === 'details' && (
        <ModalFrame title={modal.camera.name} close={() => setModal(null)}>
          <p className="nv-muted">
            {modal.camera.building} · {modal.camera.floor}
          </p>
          <p>
            {modal.camera.result?.conflict?.explanation ||
              'No current analysis is available.'}
          </p>
          {modal.camera.error && (
            <p role="alert" className="nv-warning">
              {modal.camera.error}
            </p>
          )}
          <dl>
            <dt>Feed</dt>
            <dd>{connected ? modal.camera.feed : 'disconnected'}</dd>
            <dt>Coverage</dt>
            <dd>{connected ? coverageLabel(modal.camera) : 'Unavailable'}</dd>
            <dt>Last inference</dt>
            <dd>
              {modal.camera.result
                ? `${Math.round(modal.camera.result.inferenceMs)} ms (processing only)`
                : 'Not available'}
            </dd>
            <dt>People analyzed</dt>
            <dd>
              {modal.camera.result?.coverage?.analyzedPeople ?? 'Not available'}
            </dd>
          </dl>
          <div className="nv-actions">
            <button
              className="nv-primary"
              disabled={!connected || !modal.camera.enabled || busy}
              onClick={() => pair(modal.camera)}
            >
              Pair device
            </button>
            <button
              className="nv-secondary"
              disabled={!connected || busy}
              onClick={() => toggleCamera(modal.camera)}
            >
              {modal.camera.enabled ? 'Pause camera' : 'Enable camera'}
            </button>
            <button
              className="nv-text-button"
              onClick={() => setModal({ type: 'camera', camera: modal.camera })}
            >
              Edit location
            </button>
          </div>
        </ModalFrame>
      )}
    </div>
  )
}
