import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { ArrowRight, Check, Copy, MapPin, Plus, Trash, UploadSimple, VideoCamera } from '@phosphor-icons/react'
import { api, type CameraLocation, type Incident } from '../classroom/contracts'
import { useClassroom } from '../classroom/useClassroom'
import { useSession } from '../auth/context'
import { roleLabel, type Role } from '../auth/session'
import { liveCameras, liveGuards, stageOf, type WallCamera } from '../command/model'
import { mapFloor } from '../command/siteMap'
import type { FloorRecord, GuardRecord, MapFloor, Placement } from '../command/types'
import { PlanEditor, type CameraGeometry } from './PlanEditor'
import '../command/command.css'
import './setup.css'

type StepId = 'site' | 'floors' | 'cameras' | 'guards' | 'test'
const STEPS: { id: StepId; title: string; lead: string }[] = [
  { id: 'site', title: 'Site', lead: 'Name the place NIVRA protects.' },
  { id: 'floors', title: 'Floors and plans', lead: 'Add each floor and upload its floor plan image.' },
  { id: 'cameras', title: 'Cameras', lead: 'Pair each phone, then drag it to where it is mounted and turn its view cone.' },
  { id: 'guards', title: 'Guards', lead: 'Invite guards and reviewers, then drag each guard to their post.' },
  { id: 'test', title: 'Test alert', lead: 'Send a labelled test incident and ring a guard’s phone end to end.' },
]
interface Member {
  userId: string
  email: string | null
  name: string | null
  role: Role
  guardCallsign: string | null
  lastActiveAt: number | null
}

const stepFromHash = (): StepId => {
  const value = location.hash.slice(1)
  return (STEPS.find((s) => s.id === value)?.id ?? 'site') as StepId
}
const messageOf = (reason: unknown) => (reason instanceof Error ? reason.message : 'Something went wrong. Try again.')

function useToast() {
  const [toast, setToast] = useState<{ text: string; tone: 'ok' | 'error' } | null>(null)
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(timer)
  }, [toast])
  const ok = useCallback((text: string) => setToast({ text, tone: 'ok' }), [])
  const fail = useCallback((reason: unknown) => setToast({ text: messageOf(reason), tone: 'error' }), [])
  return { toast, ok, fail }
}

export default function SetupPortal() {
  const session = useSession()
  const live = useClassroom(true, undefined, true)
  const snapshot = live.snapshot
  const [step, setStep] = useState<StepId>(stepFromHash)
  const { toast, ok, fail } = useToast()
  useEffect(() => {
    const onHash = () => setStep(stepFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = (id: StepId) => {
    history.replaceState(null, '', `#${id}`)
    setStep(id)
    window.scrollTo({ top: 0 })
  }

  const floorRecords = useMemo(() => [...(snapshot?.floors ?? [])].sort((a, b) => a.order - b.order), [snapshot?.floors])
  const floors = useMemo(() => floorRecords.map(mapFloor), [floorRecords])
  const floorMap = useMemo(() => new Map(floors.map((f) => [f.id, f])), [floors])
  const cameraRecords = useMemo(() => snapshot?.cameras ?? [], [snapshot?.cameras])
  const cameras = useMemo(() => liveCameras(cameraRecords, floorMap, live.previews, {}), [cameraRecords, floorMap, live.previews])
  const guardRecords = useMemo(() => snapshot?.guards ?? [], [snapshot?.guards])
  const guards = useMemo(() => liveGuards(guardRecords, floorMap), [guardRecords, floorMap])
  const events = useMemo(() => snapshot?.events ?? [], [snapshot?.events])
  const siteName = snapshot?.site?.name ?? ''

  const done: Record<StepId, boolean> = {
    site: Boolean(siteName),
    floors: floors.some((f) => f.sample || f.planUrl),
    cameras: cameras.some((c) => c.slot),
    guards: guards.some((g) => g.x != null),
    test: events.some((e) => e.model === 'test' && (e.guard_ack_at || e.on_scene_at)),
  }
  const ready = Math.round((Object.values(done).filter(Boolean).length / STEPS.length) * 100)
  const index = STEPS.findIndex((s) => s.id === step)
  const current = STEPS[index]
  const stepSummary: Record<StepId, string> = {
    site: siteName || 'Not named yet',
    floors: floors.length ? `${floors.length} floor${floors.length === 1 ? '' : 's'}` : 'No floors yet',
    cameras: `${cameras.filter((c) => c.slot).length} of ${cameras.length} placed`,
    guards: guards.length ? `${guards.length} guard${guards.length === 1 ? '' : 's'}` : 'Invite and set posts',
    test: done.test ? 'Guard phone rang' : 'Ring a guard phone',
  }

  return (
    <div className="st-app">
      <a className="cm-skip" href="#st-main">
        Skip to setup
      </a>
      <header className="st-top">
        <a className="st-brand" href="/wall">
          NIVRA
        </a>
        <span className="st-title">Set up {siteName || 'your site'}</span>
        {session.mode === 'dev' && <span className="cm-pill cm-pill--amber">Developer sign-in</span>}
        {live.connection !== 'connected' && (
          <span className="cm-pill cm-pill--amber" role="status">
            {live.connection === 'connecting' ? 'Connecting…' : 'Disconnected'}
          </span>
        )}
        <span className="st-user">
          {session.me?.name ?? session.me?.email} · {roleLabel(session.me?.role ?? 'admin')}
        </span>
        <a className="cm-btn" href="/wall">
          Open Command
        </a>
        <button type="button" className="cm-btn cm-btn--quiet" onClick={() => void session.signOut()}>
          Sign out
        </button>
      </header>
      {live.error && (
        <p className="cm-banner cm-banner--warn" role="alert">
          {live.error}
        </p>
      )}

      <div className="st-body">
        <nav className="st-rail" aria-label="Setup steps">
          <ol>
            {STEPS.map((s, i) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={`${s.id === step ? 'is-current' : ''} ${done[s.id] ? 'is-done' : ''}`}
                  aria-current={s.id === step ? 'step' : undefined}
                  onClick={() => go(s.id)}
                >
                  <span className="st-num" aria-hidden>
                    {done[s.id] && s.id !== step ? <Check weight="bold" /> : i + 1}
                  </span>
                  <span>
                    <strong>{s.title}</strong>
                    <small>{stepSummary[s.id]}</small>
                  </span>
                  {done[s.id] && <span className="cm-sr-only">(done)</span>}
                </button>
              </li>
            ))}
          </ol>
          <div className="st-progress">
            <span>{ready}% ready</span>
            <div aria-hidden>
              <i style={{ width: `${ready}%` }} />
            </div>
          </div>
        </nav>

        <main id="st-main" className="st-main">
          <header className="st-head">
            <h1>
              {index + 1} · {current.title}
            </h1>
            <p className="cm-muted">{current.lead}</p>
          </header>
          {!snapshot ? (
            <p role="status" className="cm-muted">
              {live.connection === 'connected' ? 'Loading site…' : 'Connecting to the NIVRA service…'}
            </p>
          ) : step === 'site' ? (
            <SiteStep name={siteName} ok={ok} fail={fail} mode={session.mode} />
          ) : step === 'floors' ? (
            <FloorsStep floors={floorRecords} siteName={siteName} ok={ok} fail={fail} />
          ) : step === 'cameras' ? (
            <CamerasStep floors={floors} cameras={cameras} records={cameraRecords} guards={guards} siteName={siteName} ok={ok} fail={fail} />
          ) : step === 'guards' ? (
            <GuardsStep floors={floors} guards={guards} records={guardRecords} cameras={cameras} ok={ok} fail={fail} />
          ) : (
            <TestStep cameras={cameras} events={events} guards={guardRecords} ok={ok} fail={fail} />
          )}
          <footer className="st-foot">
            <button type="button" className="cm-btn" disabled={index === 0} onClick={() => go(STEPS[index - 1].id)}>
              Back
            </button>
            {index < STEPS.length - 1 ? (
              <button type="button" className="cm-btn cm-btn--dark" onClick={() => go(STEPS[index + 1].id)}>
                Continue to {STEPS[index + 1].title} <ArrowRight aria-hidden />
              </button>
            ) : (
              <a className="cm-btn cm-btn--dark" href="/wall">
                Finish and open Command <ArrowRight aria-hidden />
              </a>
            )}
          </footer>
        </main>
      </div>
      {toast && (
        <p className={`st-toast ${toast.tone === 'error' ? 'is-error' : ''}`} role={toast.tone === 'error' ? 'alert' : 'status'}>
          {toast.text}
        </p>
      )}
    </div>
  )
}

type Notify = { ok: (text: string) => void; fail: (reason: unknown) => void }

function Card({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="st-card">
      <header>
        <h2>{title}</h2>
        {actions}
      </header>
      {children}
    </section>
  )
}

/* ---------------- 1 · Site ---------------- */

function SiteStep({ name, ok, fail, mode }: Notify & { name: string; mode: 'clerk' | 'dev' }) {
  const [value, setValue] = useState(name)
  const [busy, setBusy] = useState(false)
  const save = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      await api('/site', 'PATCH', { name: value.trim() })
      ok('Site name saved.')
    } catch (reason) {
      fail(reason)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="st-grid2">
      <Card title="Site name">
        <form className="st-form" onSubmit={(e) => void save(e)}>
          <label>
            <span>Shown on Command and on guard phones</span>
            <input value={value} maxLength={60} required onChange={(e) => setValue(e.target.value)} placeholder="Orbit Mall" />
          </label>
          <button className="cm-btn cm-btn--dark" disabled={busy || !value.trim() || value.trim() === name}>
            {busy ? 'Saving…' : 'Save name'}
          </button>
        </form>
      </Card>
      <Card title="Sign-in">
        {mode === 'clerk' ? (
          <p>Reviewers sign in at <code>/login</code>, guards at <code>/guard</code>. Invite people in step 4.</p>
        ) : (
          <p>
            <strong>Developer sign-in is on</strong> because Clerk keys are not set. Anyone who can open this computer’s address can pick a
            role. Add <code>VITE_CLERK_PUBLISHABLE_KEY</code> and <code>CLERK_SECRET_KEY</code> to <code>.env.local</code> before a real
            deployment.
          </p>
        )}
      </Card>
    </div>
  )
}

/* ---------------- 2 · Floors ---------------- */

function FloorsStep({ floors, siteName, ok, fail }: Notify & { floors: FloorRecord[]; siteName: string }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const add = async (event: FormEvent) => {
    event.preventDefault()
    setBusy('add')
    try {
      await api('/floors', 'POST', { name: name.trim() })
      setName('')
      ok('Floor added. Upload its plan next.')
    } catch (reason) {
      fail(reason)
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className="st-floors">
      {floors.map((floor) => (
        <FloorCard key={floor.id} floor={floor} siteName={siteName} ok={ok} fail={fail} />
      ))}
      <form className="st-card st-add" onSubmit={(e) => void add(e)}>
        <h2>Add a floor</h2>
        <label className="st-form">
          <span>Floor name</span>
          <input value={name} maxLength={60} placeholder={floors.length ? `Floor ${floors.length + 1}` : 'Ground floor'} onChange={(e) => setName(e.target.value)} required />
        </label>
        <button className="cm-btn cm-btn--dark" disabled={busy === 'add' || !name.trim()}>
          <Plus aria-hidden /> Add floor
        </button>
      </form>
    </div>
  )
}

function FloorCard({ floor, ok, fail }: Notify & { floor: FloorRecord; siteName: string }) {
  const map = mapFloor(floor)
  const widthMeters = floor.metersPerUnit && floor.plan ? Math.round(floor.metersPerUnit * floor.plan.width) : ''
  const [name, setName] = useState(floor.name)
  const [width, setWidth] = useState(String(widthMeters))
  const [busy, setBusy] = useState(false)
  const run = async (action: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await action()
      ok(message)
    } catch (reason) {
      fail(reason)
    } finally {
      setBusy(false)
    }
  }
  const upload = (file: File | undefined) => {
    if (!file) return
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) return fail(new Error('Use a PNG, JPEG or WebP image.'))
    if (file.size > 8 * 1024 * 1024) return fail(new Error('Floor plans must be 8 MB or smaller.'))
    const form = new FormData()
    form.append('file', file)
    void run(() => api(`/floors/${floor.id}/plan`, 'PUT', form), 'Floor plan uploaded.')
  }
  const saveDetails = (event: FormEvent) => {
    event.preventDefault()
    const meters = Number(width)
    const metersPerUnit = floor.plan && meters > 0 ? meters / floor.plan.width : null
    void run(() => api(`/floors/${floor.id}`, 'PATCH', { name: name.trim(), order: floor.order, metersPerUnit }), 'Floor saved.')
  }
  return (
    <section className="st-card st-floor">
      <div className="st-floor-preview">
        {floor.plan || floor.sample ? (
          <FloorThumb floor={map} />
        ) : (
          <label className="st-drop">
            <UploadSimple aria-hidden />
            <span>Upload a floor plan</span>
            <small>PNG, JPEG or WebP · up to 8 MB</small>
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => upload(e.target.files?.[0])} />
          </label>
        )}
      </div>
      <form className="st-form" onSubmit={saveDetails}>
        <label>
          <span>Name</span>
          <input value={name} maxLength={60} required onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          <span>Floor width in metres (for walking distances)</span>
          <input
            type="number"
            min={5}
            max={2000}
            step={1}
            inputMode="numeric"
            value={width}
            disabled={!floor.plan || floor.sample}
            placeholder={floor.sample ? '96 (sample)' : floor.plan ? 'e.g. 80' : 'Upload a plan first'}
            onChange={(e) => setWidth(e.target.value)}
          />
        </label>
        <div className="cm-row">
          <button className="cm-btn cm-btn--dark" disabled={busy}>
            Save
          </button>
          {(floor.plan || floor.sample) && (
            <label className="cm-btn st-file">
              <UploadSimple aria-hidden /> Replace plan
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => upload(e.target.files?.[0])} />
            </label>
          )}
          {!floor.sample && (
            <button type="button" className="cm-btn" disabled={busy} onClick={() => void run(() => api(`/floors/${floor.id}/sample`, 'POST'), 'Using the sample mall plan.')}>
              Use sample mall
            </button>
          )}
          <button
            type="button"
            className="cm-btn st-danger"
            disabled={busy}
            onClick={() => {
              if (confirm(`Delete ${floor.name}? Cameras and guard posts on it become unplaced.`))
                void run(() => api(`/floors/${floor.id}`, 'DELETE'), 'Floor deleted.')
            }}
          >
            <Trash aria-hidden /> Delete
          </button>
        </div>
      </form>
    </section>
  )
}

function FloorThumb({ floor }: { floor: MapFloor }) {
  return (
    <div className="st-thumb">
      {floor.sample || !floor.planUrl ? (
        <svg viewBox={`0 0 ${floor.width} ${floor.height}`} aria-hidden>
          <rect width={floor.width} height={floor.height} fill="#f4f4f5" />
          <text x={floor.width / 2} y={floor.height / 2} textAnchor="middle" fontSize={floor.width / 18} fill="#52525b">
            Sample mall plan
          </text>
        </svg>
      ) : (
        <img src={floor.planUrl} alt={`${floor.name} floor plan`} />
      )}
    </div>
  )
}

/* ---------------- 3 · Cameras ---------------- */

function FloorTabs({ floors, value, onChange }: { floors: MapFloor[]; value: string | null; onChange: (id: string) => void }) {
  if (floors.length < 2) return null
  return (
    <div className="cm-floor-tabs" role="tablist" aria-label="Floors">
      {floors.map((floor) => (
        <button key={floor.id} type="button" role="tab" aria-selected={floor.id === value} className={floor.id === value ? 'is-on' : ''} onClick={() => onChange(floor.id)}>
          {floor.name}
        </button>
      ))}
    </div>
  )
}

function PairingPanel({ camera, onClose, fail }: { camera: CameraLocation; onClose: () => void; fail: (reason: unknown) => void }) {
  const [link, setLink] = useState<{ url: string; remoteReady: boolean; expires: number } | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [copied, setCopied] = useState(false)
  const failRef = useRef(fail)
  useEffect(() => {
    failRef.current = fail
  })
  // One code per camera; a new one only when the admin asks (pairing again revokes the old phone).
  const create = useCallback(async () => {
    try {
      const result = await api<{ url: string; remoteReady: boolean; expiresInSeconds: number }>(`/cameras/${camera.id}/pair`, 'POST')
      setLink({ url: result.url, remoteReady: result.remoteReady, expires: Date.now() + result.expiresInSeconds * 1000 })
      setCopied(false)
    } catch (reason) {
      failRef.current(reason)
    }
  }, [camera.id])
  useEffect(() => {
    void create()
  }, [create])
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const seconds = link ? Math.max(0, Math.ceil((link.expires - now) / 1000)) : 0
  return (
    <div className="st-pair">
      <header>
        <strong>Pair a phone as {camera.label ?? camera.name}</strong>
        <button type="button" className="cm-link" onClick={onClose}>
          Close
        </button>
      </header>
      {link && seconds > 0 ? (
        <div className="st-pair-body">
          <QRCodeSVG value={link.url} size={148} marginSize={2} title={`Pairing code for ${camera.name}`} />
          <div>
            <p>Scan with the phone’s camera, open the link, allow camera access and tap Start camera.</p>
            <p className="cm-muted">
              Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} · one phone only
            </p>
            {!link.remoteReady && location.protocol !== 'https:' && (
              <p className="cm-warn">Phones need HTTPS to open the camera. Use the showcase HTTPS address (see docs/mac-showcase.md).</p>
            )}
            <code className="st-link">{link.url}</code>
            <button type="button" className="cm-btn" onClick={() => void navigator.clipboard?.writeText(link.url).then(() => setCopied(true))}>
              <Copy aria-hidden /> {copied ? 'Copied' : 'Copy link'}
            </button>
          </div>
        </div>
      ) : (
        <div className="st-pair-body">
          <p className="cm-muted">{link ? 'This code expired.' : 'Creating a pairing code…'}</p>
          {link && (
            <button type="button" className="cm-btn cm-btn--dark" onClick={() => void create()}>
              New code
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function placementFor(camera: WallCamera, floor: MapFloor, patch: Partial<CameraGeometry> = {}): Placement | null {
  if (!camera.slot) return null
  return {
    floorId: floor.id,
    x: (patch.x ?? camera.slot.x) / floor.width,
    y: (patch.y ?? camera.slot.y) / floor.height,
    angle: patch.angle ?? camera.slot.angle,
    fov: camera.slot.fov,
    range: camera.slot.range / floor.width,
  }
}

function CamerasStep({
  floors,
  cameras,
  records,
  guards,
  siteName,
  ok,
  fail,
}: Notify & { floors: MapFloor[]; cameras: WallCamera[]; records: CameraLocation[]; guards: ReturnType<typeof liveGuards>; siteName: string }) {
  const [floorId, setFloorId] = useState<string | null>(null)
  const floor = floors.find((f) => f.id === floorId) ?? floors[0] ?? null
  const [selected, setSelected] = useState<string | null>(null)
  const [placing, setPlacing] = useState<string | null>(null)
  const [pairing, setPairing] = useState<string | null>(null)
  const [preview, setPreview] = useState<Record<string, Partial<CameraGeometry>>>({})
  const [newName, setNewName] = useState('')
  useEffect(() => setPreview({}), [records])

  const shown = cameras.map((camera) =>
    camera.slot && preview[camera.id] ? { ...camera, slot: { ...camera.slot, ...preview[camera.id] } } : camera,
  )
  const camera = shown.find((c) => c.id === selected) ?? null
  const record = records.find((r) => r.id === selected) ?? null

  const patch = async (id: string, body: Record<string, unknown>, message?: string) => {
    try {
      await api(`/cameras/${id}`, 'PATCH', body)
      if (message) ok(message)
    } catch (reason) {
      setPreview({})
      fail(reason)
    }
  }
  const commit = (id: string, geometry: Partial<CameraGeometry>) => {
    const target = shown.find((c) => c.id === id)
    if (!target || !floor) return
    setPreview((old) => ({ ...old, [id]: { ...old[id], ...geometry } }))
    const placement = placementFor(target, floor, geometry)
    if (placement) void patch(id, { placement })
  }
  const place = (id: string, point: { x: number; y: number }) => {
    if (!floor) return
    setPlacing(null)
    setSelected(id)
    void patch(id, { placement: { floorId: floor.id, x: point.x / floor.width, y: point.y / floor.height, angle: 90, fov: 70, range: 0.15 } }, 'Camera placed. Drag the round handle to turn it.')
  }
  const addCamera = async (event: FormEvent) => {
    event.preventDefault()
    try {
      const created = await api<CameraLocation>('/cameras', 'POST', { name: newName.trim(), building: siteName || 'Site', floor: floor?.name ?? 'Floor' })
      setNewName('')
      setPairing(created.id)
      ok(`${created.label ?? created.name} added. Scan the code with the phone.`)
    } catch (reason) {
      fail(reason)
    }
  }
  const unplaced = shown.filter((c) => !c.slot)
  const meters = floor?.metersPerUnit ?? null
  const rangeValue = camera?.slot && floor ? (meters ? Math.round(camera.slot.range * meters) : Math.round((camera.slot.range / floor.width) * 100)) : 0

  return (
    <div className="st-cams">
      <div className="st-cams-side">
        <Card title="Camera phones" actions={<span className="cm-muted">{cameras.filter((c) => c.status === 'live').length} live</span>}>
          {!cameras.length && <p className="cm-muted">No cameras yet. Add one below, then scan its code with a phone.</p>}
          <ul className="st-list">
            {shown.map((c) => (
              <li key={c.id} className={c.id === selected ? 'is-selected' : ''}>
                <button type="button" className="st-list-main" onClick={() => setSelected(c.id)}>
                  <span className="st-mini">{c.image ? <img src={c.image} alt="" /> : <VideoCamera aria-hidden />}</span>
                  <span>
                    <strong>
                      {c.label} {c.name}
                    </strong>
                    <small>
                      <i className={`st-dot is-${c.status}`} aria-hidden /> {c.slot ? 'Placed' : 'Not placed'} ·{' '}
                      {c.status === 'live' ? 'Live' : c.status === 'connecting' ? 'Connecting' : c.status === 'paused' ? 'Paused' : 'Not connected'}
                    </small>
                  </span>
                </button>
                {!c.slot && floor && (
                  <button type="button" className="cm-btn cm-btn--dark cm-btn--quiet" aria-pressed={placing === c.id} onClick={() => setPlacing(placing === c.id ? null : c.id)}>
                    {placing === c.id ? 'Cancel' : 'Place on map'}
                  </button>
                )}
              </li>
            ))}
          </ul>
          <form className="st-inline" onSubmit={(e) => void addCamera(e)}>
            <label>
              <span className="cm-sr-only">New camera name</span>
              <input value={newName} maxLength={50} required placeholder="Camera name, e.g. Atrium East" onChange={(e) => setNewName(e.target.value)} />
            </label>
            <button className="cm-btn" disabled={!newName.trim()}>
              <Plus aria-hidden /> Add camera
            </button>
          </form>
        </Card>
        {pairing && records.find((r) => r.id === pairing) && (
          <PairingPanel camera={records.find((r) => r.id === pairing)!} onClose={() => setPairing(null)} fail={fail} />
        )}
      </div>

      <div className="st-cams-main">
        {!floor ? (
          <div className="cm-empty-map">
            <strong>Add a floor first</strong>
            <span className="cm-muted">Cameras are placed on a floor plan.</span>
            <a className="cm-btn cm-btn--dark" href="#floors">
              Go to Floors
            </a>
          </div>
        ) : (
          <section className="st-card st-editor-card">
            <header>
              <h2>{floor.name}</h2>
              <FloorTabs floors={floors} value={floor.id} onChange={(id) => { setFloorId(id); setSelected(null) }} />
            </header>
            <PlanEditor
              floor={floor}
              cameras={shown}
              guards={guards}
              mode="camera"
              selected={selected}
              placing={placing}
              onSelect={setSelected}
              onPreview={(id, g) => setPreview((old) => ({ ...old, [id]: { ...old[id], ...g } }))}
              onCommit={commit}
              onPlace={place}
              label={`${floor.name} camera layout`}
            />
            <p className="st-hint" aria-live="polite">
              {placing
                ? `Click where ${shown.find((c) => c.id === placing)?.label ?? 'the camera'} is mounted.`
                : unplaced.length
                  ? `Drag to move · drag the round handle to turn · ${unplaced.length} camera${unplaced.length === 1 ? '' : 's'} not placed`
                  : 'Drag to move · drag the round handle to turn · arrow keys and [ ] also work'}
            </p>
          </section>
        )}
      </div>

      {camera && record && floor && (
        <aside className="st-inspector" aria-label={`${camera.label} settings`}>
          <h2>
            {camera.label} · {camera.name}
          </h2>
          <p className="cm-muted">
            <i className={`st-dot is-${camera.status}`} aria-hidden /> {camera.status === 'live' ? 'Live' : 'Not streaming'}
            {record.compute ? ` · analysis on ${record.compute === 'device' ? 'the phone' : 'this computer'}` : ''}
          </p>
          <form
            className="st-form"
            onSubmit={(e) => {
              e.preventDefault()
              const value = new FormData(e.currentTarget).get('name')
              if (typeof value === 'string' && value.trim()) void patch(camera.id, { name: value.trim() }, 'Name saved.')
            }}
          >
            <label>
              <span>Name</span>
              <input name="name" defaultValue={camera.name} key={camera.name} maxLength={50} required />
            </label>
            <button className="cm-btn">Save name</button>
          </form>
          {camera.slot ? (
            <div className="st-form">
              <label>
                <span>Direction · {Math.round(camera.slot.angle)}°</span>
                <input type="range" min={0} max={359} value={Math.round(camera.slot.angle)} onChange={(e) => setPreview((old) => ({ ...old, [camera.id]: { ...old[camera.id], angle: Number(e.target.value) } }))} onPointerUp={(e) => commit(camera.id, { angle: Number((e.target as HTMLInputElement).value) })} onKeyUp={(e) => commit(camera.id, { angle: Number((e.target as HTMLInputElement).value) })} />
              </label>
              <label>
                <span>Field of view · {Math.round(camera.slot.fov)}°</span>
                <input
                  type="range"
                  min={10}
                  max={170}
                  defaultValue={Math.round(camera.slot.fov)}
                  key={`fov-${camera.id}-${camera.slot.fov}`}
                  onChange={(e) => {
                    const placement = placementFor(camera, floor)
                    if (placement) void patch(camera.id, { placement: { ...placement, fov: Number(e.target.value) } })
                  }}
                />
              </label>
              <label>
                <span>
                  Range · {rangeValue} {meters ? 'm' : '% of plan width'}
                </span>
                <input
                  type="range"
                  min={meters ? 2 : 2}
                  max={meters ? Math.max(10, Math.round(floor.width * meters)) : 100}
                  defaultValue={rangeValue}
                  key={`range-${camera.id}-${camera.slot.range}`}
                  onChange={(e) => {
                    const value = Number(e.target.value)
                    const range = meters ? value / meters / floor.width : value / 100
                    const placement = placementFor(camera, floor)
                    if (placement) void patch(camera.id, { placement: { ...placement, range: Math.min(1, Math.max(0.02, range)) } })
                  }}
                />
              </label>
            </div>
          ) : (
            <p className="cm-muted">
              <MapPin aria-hidden /> Not on the map yet. Use “Place on map”, then click where it is mounted.
            </p>
          )}
          {camera.image && <img className="st-live" src={camera.image} alt={`Live view from ${camera.name}`} />}
          <div className="cm-row">
            <button type="button" className="cm-btn" onClick={() => setPairing(camera.id)}>
              Pair a phone
            </button>
            {camera.slot && (
              <button type="button" className="cm-btn st-danger" onClick={() => void patch(camera.id, { placement: null }, 'Removed from the map.')}>
                Remove from map
              </button>
            )}
          </div>
        </aside>
      )}
    </div>
  )
}

/* ---------------- 4 · Guards ---------------- */

function GuardsStep({
  floors,
  guards,
  records,
  cameras,
  ok,
  fail,
}: Notify & { floors: MapFloor[]; guards: ReturnType<typeof liveGuards>; records: GuardRecord[]; cameras: WallCamera[] }) {
  const { mode } = useSession()
  const [members, setMembers] = useState<Member[]>([])
  const [selected, setSelected] = useState<string | null>(location.hash === '#guards' ? null : null)
  const [preview, setPreview] = useState<Record<string, { x: number; y: number }>>({})
  const [form, setForm] = useState({ name: '', email: '', callsign: '' })
  const [invite, setInvite] = useState({ email: '', role: 'reviewer' as Role })
  const loadMembers = useCallback(async () => {
    try {
      setMembers(await api<Member[]>('/members'))
    } catch {
      setMembers([])
    }
  }, [])
  useEffect(() => {
    void loadMembers()
  }, [loadMembers, records])
  useEffect(() => setPreview({}), [records])

  const nextCallsign = useMemo(() => {
    const used = new Set(records.map((r) => r.callsign))
    for (let i = 1; i < 100; i++) if (!used.has(`G${i}`)) return `G${i}`
    return 'G99'
  }, [records])
  const record = records.find((r) => r.callsign === selected) ?? null
  const floor = floors.find((f) => f.id === record?.floorId) ?? floors[0] ?? null
  const shown = guards.map((g) => (preview[g.id] ? { ...g, ...preview[g.id] } : g))

  const patchGuard = async (id: string, body: Record<string, unknown>, message?: string) => {
    try {
      await api(`/guards/${id}`, 'PATCH', body)
      if (message) ok(message)
    } catch (reason) {
      setPreview({})
      fail(reason)
    }
  }
  const addGuard = async (event: FormEvent) => {
    event.preventDefault()
    const callsign = (form.callsign.trim() || nextCallsign).toUpperCase()
    try {
      await api('/guards', 'POST', {
        callsign,
        name: form.name.trim(),
        ...(form.email.trim() ? { email: form.email.trim().toLowerCase() } : {}),
        ...(floors[0] ? { floorId: floors[0].id } : {}),
      })
      setForm({ name: '', email: '', callsign: '' })
      setSelected(callsign)
      ok(form.email.trim() ? `${callsign} added and invited. Drag them to their post.` : `${callsign} added. Drag them to their post.`)
    } catch (reason) {
      fail(reason)
    }
  }
  const sendInvite = async (event: FormEvent) => {
    event.preventDefault()
    try {
      await api('/members/invite', 'POST', { email: invite.email.trim().toLowerCase(), role: invite.role })
      setInvite({ email: '', role: 'reviewer' })
      void loadMembers()
      ok(`Invite sent to ${invite.email.trim()}.`)
    } catch (reason) {
      fail(reason)
    }
  }
  const setPost = (callsign: string, point: { x: number; y: number }) => {
    const target = records.find((r) => r.callsign === callsign)
    if (!target || !floor) return
    setPreview((old) => ({ ...old, [callsign]: point }))
    void patchGuard(target.id, { floorId: floor.id, post: { x: point.x / floor.width, y: point.y / floor.height } })
  }
  const staff = members.filter((m) => m.role !== 'guard')

  return (
    <div className="st-people">
      <section className="st-card st-table-card">
        <header>
          <h2>Guards · {records.length}</h2>
        </header>
        <div className="st-table-wrap">
          <table className="st-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Call sign</th>
                <th scope="col">Post</th>
                <th scope="col">Shift</th>
                <th scope="col">Phone</th>
              </tr>
            </thead>
            <tbody>
              {records.map((g) => (
                <tr key={g.id} className={g.callsign === selected ? 'is-selected' : ''}>
                  <th scope="row">
                    <button type="button" className="st-row-btn" onClick={() => setSelected(g.callsign)} aria-pressed={g.callsign === selected}>
                      {g.name}
                      <small>{g.email ?? 'No email'}</small>
                    </button>
                  </th>
                  <td>{g.callsign}</td>
                  <td>{g.post ? floors.find((f) => f.id === g.floorId)?.name ?? 'Placed' : 'Not set'}</td>
                  <td>{g.shift === 'on_shift' ? 'On shift' : g.shift === 'break' ? 'Break' : 'Off'}</td>
                  <td>
                    <i className={`st-dot ${g.presence?.online ? 'is-live' : ''}`} aria-hidden />{' '}
                    {g.presence?.online ? 'Online' : g.userId ? 'Signed up' : 'Invited'}
                    {g.push ? ' · alerts on' : ''}
                  </td>
                </tr>
              ))}
              {!records.length && (
                <tr>
                  <td colSpan={5} className="cm-muted">
                    No guards yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <form className="st-inline st-inline--wrap" onSubmit={(e) => void addGuard(e)}>
          <label>
            <span>Name</span>
            <input value={form.name} maxLength={60} required onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>
            <span>Email {mode === 'clerk' ? '(sends an invite)' : '(optional)'}</span>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label className="st-short">
            <span>Call sign</span>
            <input value={form.callsign} placeholder={nextCallsign} pattern="[Gg][0-9]{1,2}" maxLength={3} onChange={(e) => setForm({ ...form, callsign: e.target.value })} />
          </label>
          <button className="cm-btn cm-btn--dark" disabled={!form.name.trim()}>
            <Plus aria-hidden /> Add guard
          </button>
        </form>
        {mode === 'dev' && <p className="cm-muted st-small">Developer sign-in: a guard opens /guard and signs in with their call sign, e.g. G2.</p>}

        <h2 className="st-sub">Reviewers and admins</h2>
        <ul className="st-staff">
          {staff.map((m) => (
            <li key={m.userId}>
              <span>
                <strong>{m.name ?? m.email}</strong>
                <small>{m.email}</small>
              </span>
              <span className="cm-tag">{roleLabel(m.role)}</span>
            </li>
          ))}
          {!staff.length && <li className="cm-muted">Only you so far.</li>}
        </ul>
        <form className="st-inline st-inline--wrap" onSubmit={(e) => void sendInvite(e)}>
          <label>
            <span>Invite by email</span>
            <input type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
          </label>
          <label className="st-short">
            <span>Role</span>
            <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value as Role })}>
              <option value="reviewer">Reviewer</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <button className="cm-btn">Send invite</button>
        </form>
      </section>

      <section className="st-card st-editor-card">
        <header>
          <h2>{record ? `${record.name} · ${record.callsign}` : 'Guard posts'}</h2>
          {record && <span className="cm-muted">Post on {floor?.name ?? 'no floor'}</span>}
        </header>
        {!floor ? (
          <p className="cm-muted">Add a floor plan first.</p>
        ) : (
          <>
            <PlanEditor
              floor={floor}
              cameras={cameras}
              guards={shown.filter((g) => !record || g.floorId === floor.id)}
              mode="guard"
              selected={selected}
              placing={record && (record.floorId !== floor.id || !record.post) ? record.callsign : null}
              onSelect={(id) => id && setSelected(id)}
              onPreview={(id, g) => g.x != null && g.y != null && setPreview((old) => ({ ...old, [id]: { x: g.x!, y: g.y! } }))}
              onCommit={(id, g) => {
                const current = shown.find((s) => s.id === id)
                setPost(id, { x: g.x ?? current?.x ?? 0, y: g.y ?? current?.y ?? 0 })
              }}
              onPlace={(id, point) => setPost(id, point)}
              label={`${floor.name} guard posts`}
            />
            <p className="st-hint">
              {record && !record.post ? `Click where ${record.callsign} stands.` : `Drag a guard to their post. Command uses posts to suggest the nearest guard.`}
            </p>
            {record && (
              <div className="cm-row">
                <button
                  type="button"
                  className="cm-btn st-danger"
                  onClick={() => {
                    if (confirm(`Remove ${record.name} (${record.callsign})? Their phone stops receiving alerts.`))
                      void api(`/guards/${record.id}`, 'DELETE').then(() => {
                        setSelected(null)
                        ok(`${record.callsign} removed.`)
                      }, fail)
                  }}
                >
                  Remove guard
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  )
}

/* ---------------- 5 · Test alert ---------------- */

function TestStep({ cameras, events, guards, ok, fail }: Notify & { cameras: WallCamera[]; events: Incident[]; guards: GuardRecord[] }) {
  const [cameraId, setCameraId] = useState(cameras[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const latest = events.filter((e) => e.model === 'test').sort((a, b) => b.received_at - a.received_at)[0] ?? null
  const ready = guards.filter((g) => g.shift === 'on_shift' && g.presence?.online)
  const send = async () => {
    setBusy(true)
    try {
      await api('/events/test', 'POST', { cameraId })
      ok('Test incident sent. Open Command to review it.')
    } catch (reason) {
      fail(reason)
    } finally {
      setBusy(false)
    }
  }
  const stage = latest ? stageOf(latest) : null
  const checks = [
    { label: 'A guard phone is online and on shift', done: ready.length > 0, detail: ready.length ? ready.map((g) => g.callsign).join(', ') : 'Open /guard on a phone and tap Start shift' },
    { label: 'Command received the test incident', done: Boolean(latest) },
    { label: 'Reviewer confirmed and alerted a guard', done: Boolean(latest?.alerted_at) },
    { label: 'Guard acknowledged on their phone', done: Boolean(latest?.guard_ack_at) },
  ]
  return (
    <div className="st-grid2">
      <Card title="Send a test incident">
        <div className="st-form">
          <label>
            <span>Camera</span>
            <select value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label} {c.name}
                </option>
              ))}
            </select>
          </label>
          <p className="cm-muted">It appears on Command labelled as a test. Confirm it and alert a guard: their phone should ring for 4 seconds.</p>
          <div className="cm-row">
            <button type="button" className="cm-btn cm-btn--dark" disabled={busy || !cameraId} onClick={() => void send()}>
              Send test incident
            </button>
            <a className="cm-btn" href="/wall" target="_blank" rel="noreferrer">
              Open Command
            </a>
          </div>
        </div>
      </Card>
      <Card title="End-to-end check">
        <ol className="st-checks">
          {checks.map((check) => (
            <li key={check.label} className={check.done ? 'is-done' : ''}>
              <span className="st-num" aria-hidden>
                {check.done ? <Check weight="bold" /> : ''}
              </span>
              <span>
                {check.label}
                {check.detail && <small>{check.detail}</small>}
              </span>
              <span className="cm-sr-only">{check.done ? 'done' : 'not yet'}</span>
            </li>
          ))}
        </ol>
        {stage && <p className="cm-muted">Latest test: {stage.replace('_', ' ')}.</p>}
      </Card>
    </div>
  )
}
