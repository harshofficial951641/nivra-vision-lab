import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { ArrowRight, Camera, Check, Plus, ShieldCheck } from '@phosphor-icons/react'
import { api, type CameraLocation, type Incident } from '../classroom/contracts'
import { useClassroom } from '../classroom/useClassroom'
import { useSession } from '../auth/context'
import { roleLabel, type Role } from '../auth/session'
import { liveCameras, stageOf, type WallCamera } from '../command/model'
import { mapFloor } from '../command/siteMap'
import type { GuardRecord } from '../command/types'
import { GoogleMap } from '../location/GoogleMap'
import '../command/command.css'
import './setup.css'
import { PairingPanel } from './PairingPanel'
import { Brand } from '../ui/Brand'

type StepId = 'site' | 'cameras' | 'guards' | 'test'
const STEPS: { id: StepId; title: string; lead: string }[] = [
  { id: 'site', title: 'Site', lead: 'Name the place NIVRA protects.' },
  { id: 'cameras', title: 'Cameras', lead: 'Add a camera, then scan its QR with your phone.' },
  { id: 'guards', title: 'Guards', lead: 'Add your team now, or do it later.' },
  { id: 'test', title: 'Test alert', lead: 'Check that an alert reaches a guard.' },
]
interface Member {
  userId: string
  email: string | null
  name: string | null
  role: Role
  guardCallsign: string | null
  lastActiveAt: number | null
}

const stepFromHash = (named = false): StepId => {
  const value = location.hash.slice(1)
  return (STEPS.find((s) => s.id === value)?.id ?? (value === 'launch' ? 'test' : named ? 'cameras' : 'site')) as StepId
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
  const [step, setStep] = useState<StepId>(() => stepFromHash(!!snapshot?.site?.name))
  const choseSection = useRef(!!location.hash)
  useEffect(() => { if (!choseSection.current && snapshot?.site?.name) setStep('cameras') }, [snapshot?.site?.name])
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [step])
  const { toast, ok, fail } = useToast()
  useEffect(() => {
    const onHash = () => {
      if (location.hash === '#st-main') return
      choseSection.current = !!location.hash
      setStep(stepFromHash(!!live.snapshot?.site?.name))
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [live.snapshot?.site?.name])
  const go = (id: StepId) => {
    choseSection.current = true
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
  const events = useMemo(() => snapshot?.events ?? [], [snapshot?.events])
  const siteName = snapshot?.site?.name ?? ''

  const index = STEPS.findIndex((s) => s.id === step)
  const current = STEPS[index]


  return (
    <div className="st-app st-simple">
      <a className="cm-skip" href="#st-main">
        Skip to setup
      </a>
      <header className="st-top">
        <a className="st-brand" href="/mobile" aria-label="NIVRA home"><Brand /></a>
        <span className="st-title">{siteName || 'Your place'}</span>
        <a className="st-wall-link" href="/wall">Watch cameras <ArrowRight aria-hidden /></a>
      </header>
      {live.error && (
        <p className="cm-banner cm-banner--warn" role="alert">
          {live.error}
        </p>
      )}

      <div className="st-body">
        <nav className="st-rail" aria-label="Setup steps">
          <button type="button" className={step === 'cameras' ? 'is-current' : ''} aria-current={step === 'cameras' ? 'page' : undefined} onClick={() => go('cameras')}>Cameras</button>
          <details className="st-more-sections" open={step !== 'cameras' || undefined}><summary>More options</summary><ol>{STEPS.filter(s => s.id !== 'cameras').map(s => <li key={s.id}><button type="button" className={s.id === step ? 'is-current' : ''} aria-current={s.id === step ? 'page' : undefined} onClick={() => go(s.id)}>{s.id === 'guards' ? 'Guards (optional)' : s.title}</button></li>)}</ol></details>
        </nav>

        <main id="st-main" className="st-main">
          <header className="st-head" key={step}>
            <h1 ref={heading} tabIndex={-1}>{current.title}</h1>
            <p className="cm-muted">{current.lead}</p>
          </header>
          {!snapshot ? (
            <p role="status" className="cm-muted">
              {live.connection === 'connected' ? 'Loading site…' : 'Connecting to the NIVRA service…'}
            </p>
          ) : step === 'site' ? (
            <SiteStep name={siteName} ok={ok} fail={fail} mode={session.mode} privateWorkspace={!!session.me?.workspace} />

          ) : step === 'cameras' ? (
            <CamerasStep cameras={cameras} records={cameraRecords} siteName={siteName} ok={ok} fail={fail} />
          ) : step === 'guards' ? (
            <GuardsStep records={guardRecords} ok={ok} fail={fail} />
          ) : (
            <TestStep cameras={cameras} events={events} guards={guardRecords} ok={ok} fail={fail} />
          )}

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

function SiteStep({ name, ok, fail, mode, privateWorkspace }: Notify & { name: string; mode: 'clerk' | 'dev'; privateWorkspace: boolean }) {
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
      <details className="st-maintenance"><summary>Owner access & sign-in</summary><Card title="Sign-in">
        {mode === 'clerk' ? (
          <p>Reviewers sign in at <code>/login</code>, guards at <code>/guard</code>. Invite people in Guards.</p>
        ) : privateWorkspace ? (
          <p>Your private workspace is saved in this browser. Pair each phone with its own QR. Owner verification can be added later.</p>
        ) : import.meta.env.VITE_NIVRA_DIRECT_SOCKET_RELAY === '1' ? (
          <p>This site uses private owner links and device QR codes. Create owner access on the NIVRA computer. Pair each camera and guard phone with its own QR.</p>
        ) : (
          <p>
            <strong>Developer sign-in is on</strong> because Clerk keys are not set. Anyone who can open this computer’s address can pick a
            role. Add <code>VITE_CLERK_PUBLISHABLE_KEY</code> and <code>CLERK_SECRET_KEY</code> to <code>.env.local</code> before a real
            deployment.
          </p>
        )}
      </Card></details>
    </div>
  )
}

function CamerasStep({ cameras, records, siteName, ok, fail }: Notify & { cameras: WallCamera[]; records: CameraLocation[]; siteName: string }) {
  const [locationId, setLocationId] = useState<string | null>(null)
  const [pairing, setPairing] = useState<CameraLocation | null>(null)
  const [created, setCreated] = useState<CameraLocation | null>(null)
  const [busy, setBusy] = useState(false)
  const [removed, setRemoved] = useState<Set<string>>(() => new Set())
  const observedIds = useRef(new Set(records.map(record => record.id)))
  useEffect(() => {
    if (created && records.some(record => record.id === created.id)) setCreated(null)
    if (pairing && ((observedIds.current.has(pairing.id) && !records.some(record => record.id === pairing.id)) || records.some(record => record.id === pairing.id && !record.enabled))) {
      setPairing(null)
      fail(new Error('This camera was removed or paused. Choose another camera or add one below.'))
    }
    observedIds.current = new Set(records.map(record => record.id))
  }, [records, created, pairing, fail])
  const listed = records.filter(record => !removed.has(record.id))
  if (created && !removed.has(created.id) && !listed.some(record => record.id === created.id)) listed.push(created)
  const add = async () => {
    if (busy) return
    let number = 1
    const names = new Set(listed.map(record => record.name.toLowerCase()))
    while (names.has(`camera ${number}`)) number++
    setBusy(true)
    try {
      const result = await api<CameraLocation>('/cameras', 'POST', { name: `Camera ${number}`, building: siteName || 'NIVRA', floor: 'Not set' })
      setCreated(result)
      setPairing(result)
    } catch (reason) { fail(reason) } finally { setBusy(false) }
  }
  const toggle = async (record: CameraLocation) => {
    if (busy) return
    setBusy(true)
    try {
      await api(`/cameras/${record.id}`, 'PATCH', { enabled: !record.enabled })
      ok(record.enabled ? 'Camera paused.' : 'Camera is on. Connect its phone to start.')
    } catch (reason) { fail(reason) } finally { setBusy(false) }
  }
  const remove = async (record: CameraLocation) => {
    if (busy || !window.confirm(`Remove ${record.name}? Its phone will disconnect.`)) return
    setBusy(true)
    try {
      await api(`/cameras/${record.id}`, 'DELETE')
      setRemoved(previous => new Set(previous).add(record.id))
      if (created?.id === record.id) setCreated(null)
      if (locationId === record.id) setLocationId(null)
      ok(`${record.name} removed.`)
    } catch (reason) { fail(reason) }
    finally { setBusy(false) }
  }
  if (pairing) return <section className="st-connect-view" aria-label="Connect camera phone">
    {!['Not set', 'GPS location'].includes(pairing.floor) && <p className="st-device-place">{pairing.floor}</p>}
    <PairingPanel key={pairing.id} endpoint={`/cameras/${pairing.id}/pair`} label={pairing.name} kind="camera" paired={records.find(record => record.id === pairing.id)?.paired ?? pairing.paired ?? false} connected={records.some(record => record.id === pairing.id && record.feed === 'live' && record.generation !== pairing.generation)} onClose={() => setPairing(null)} fail={fail} /><a className="cm-btn cm-btn--dark st-pair-done" href="/wall">Done, watch cameras <ArrowRight aria-hidden /></a>
  </section>
  return <section className="st-devices" aria-label="Your cameras">
    {!listed.length && <div className="st-camera-empty"><span className="st-device-icon"><Camera aria-hidden size={30} /></span><h2>Use your phone as a camera.</h2><p className="cm-muted">No app to install. Keep NIVRA open in your phone's browser.</p></div>}
    <button type="button" className="cm-btn cm-btn--dark st-add-trigger" disabled={busy} onClick={() => void add()}><Plus aria-hidden /> {busy ? 'Getting ready…' : 'Add camera'}</button>
    <div className="st-device-list">
      {listed.map(record => {
        const camera = cameras.find(item => item.id === record.id)
        const floor = ['GPS location', 'Not set'].includes(record.floor) ? 'Floor not set' : record.floor
        const state = !record.enabled ? 'Paused' : record.feed === 'live' ? 'Live camera' : record.paired ? 'Phone linked' : camera?.status === 'offline' ? 'Phone offline' : 'Waiting for phone'
        return <article className="st-device-row" key={record.id}>
          <div className="st-device-heading"><span className="st-device-icon"><Camera aria-hidden size={24} /></span><div><h2>{record.name}</h2><p>{floor} · {state}</p></div>
            {record.enabled && record.feed === 'live' ? <a className="cm-btn" href="/wall">Watch</a> : record.enabled ? <button type="button" className="cm-btn" disabled={busy} onClick={() => setPairing(record)}>Connect phone</button>
              : <button type="button" className="cm-btn" disabled={busy} onClick={() => void toggle(record)}>Turn on camera</button>}
            <button type="button" className="cm-btn st-remove-camera" disabled={busy} aria-label={`Remove ${record.name}`} onClick={() => void remove(record)}>Remove</button>
          </div>
          <details className="st-device-details" onToggle={event => { if (!event.currentTarget.open && locationId === record.id) setLocationId(null) }}>
            <summary>Details</summary>
            <form className="st-form" onSubmit={event => {
              event.preventDefault()
              if (busy) return
              const data = new FormData(event.currentTarget)
              const name = String(data.get('name') ?? '').trim()
              const building = String(data.get('building') ?? '').trim()
              const floor = String(data.get('floor') ?? '').trim() || 'Not set'
              if (name && building) {
                setBusy(true)
                void api(`/cameras/${record.id}`, 'PATCH', { name, building, floor }).then(() => ok('Camera details saved.'), fail).finally(() => setBusy(false))
              }
            }}>
              <label><span>Camera name</span><input name="name" defaultValue={record.name} key={record.name} required maxLength={60} /></label>
              <label><span>Floor / area</span><input name="floor" defaultValue={floor === 'Floor not set' ? '' : floor} key={record.floor} maxLength={60} /></label>
              <details className="st-building"><summary>Change building</summary><label><span>Building / site</span><input name="building" defaultValue={record.building} key={record.building} required maxLength={60} /></label></details>
              <button className="cm-btn" disabled={busy}>Save camera details</button>
            </form>
            <div className="st-device-tools"><button type="button" className="cm-btn" onClick={() => setLocationId(locationId === record.id ? null : record.id)}>{locationId === record.id ? 'Hide location' : 'View location'}</button><button type="button" className="cm-btn" disabled={busy} onClick={() => void toggle(record)}>{record.enabled ? 'Pause camera' : 'Turn on camera'}</button></div>
            {locationId === record.id && <GoogleMap point={record.gps} label={record.name} />}
          </details>
        </article>
      })}
    </div>
    <p className="st-quiet-note">Each phone uses its own QR. Names and floors can be changed in Details.</p>
  </section>
}

/* ---------------- 4 · Guards ---------------- */

function GuardsStep({ records, ok, fail }: Notify & { records: GuardRecord[] }) {
  const { mode } = useSession()
  const [members, setMembers] = useState<Member[]>([])
  const [adding, setAdding] = useState(false)
  const [pairing, setPairing] = useState<GuardRecord | null>(null)
  const [created, setCreated] = useState<GuardRecord | null>(null)
  const [removed, setRemoved] = useState<Set<string>>(() => new Set())
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', callsign: '', floorName: '' })
  const [invite, setInvite] = useState({ email: '', role: 'reviewer' as Role })
  const listed = records.filter(record => !removed.has(record.id))
  if (created && !removed.has(created.id) && !listed.some(record => record.id === created.id)) listed.push(created)
  const nextCallsign = Array.from({ length: 99 }, (_, index) => `G${index + 1}`).find(id => !listed.some(record => record.callsign === id))
  const loadMembers = async () => {
    try { setMembers(await api<Member[]>('/members')) } catch { setMembers([]) }
  }
  const addGuard = async (event: FormEvent) => {
    event.preventDefault()
    if (busy || !form.name.trim() || !nextCallsign) return
    setBusy(true)
    try {
      const result = await api<GuardRecord>('/guards', 'POST', {
        callsign: (form.callsign.trim() || nextCallsign).toUpperCase(),
        name: form.name.trim(), floorName: form.floorName.trim() || null,
        ...(form.email.trim() ? { email: form.email.trim().toLowerCase() } : {}),
      })
      setCreated(result)
      setPairing(result)
      setAdding(false)
      setForm({ name: '', email: '', callsign: '', floorName: '' })
    } catch (reason) { fail(reason) } finally { setBusy(false) }
  }
  const removeGuard = async (record: GuardRecord) => {
    if (busy || !confirm(`Remove ${record.name}? Their phone will stop receiving alerts.`)) return
    setBusy(true)
    try {
      await api(`/guards/${record.id}`, 'DELETE')
      setRemoved(previous => new Set(previous).add(record.id))
      if (created?.id === record.id) setCreated(null)
      ok('Guard removed.')
    } catch (reason) { fail(reason) }
    finally { setBusy(false) }
  }
  const sendInvite = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    try {
      await api('/members/invite', 'POST', { email: invite.email.trim().toLowerCase(), role: invite.role })
      ok(`Invite sent to ${invite.email.trim()}.`)
      setInvite({ email: '', role: 'reviewer' })
      void loadMembers()
    } catch (reason) { fail(reason) } finally { setBusy(false) }
  }
  const teamAccess = (
    <details className="st-device-details st-team-access" onToggle={event => { if (event.currentTarget.open) void loadMembers() }}><summary>Who can watch the cameras?</summary>
      <ul className="st-staff">{members.filter(member => member.role !== 'guard').map(member => <li key={member.userId}><span><strong>{member.name ?? member.email}</strong><small>{member.email}</small></span><span>{roleLabel(member.role)}</span></li>)}</ul>
      <form className="st-form" onSubmit={event => void sendInvite(event)}><label><span>Invite by email</span><input type="email" required value={invite.email} onChange={event => setInvite({ ...invite, email: event.target.value })} /></label><label><span>Access</span><select value={invite.role} onChange={event => setInvite({ ...invite, role: event.target.value as Role })}><option value="reviewer">Watch and review</option><option value="admin">Manage this place</option></select></label><button className="cm-btn" disabled={busy}>Send invite</button></form>
    </details>
  )
  if (pairing) return <section className="st-connect-view" aria-label="Connect guard phone">{pairing.floorName && <p className="st-device-place">{pairing.floorName}</p>}<PairingPanel key={pairing.id} endpoint={`/guards/${pairing.callsign}/pair`} label={pairing.name} kind="guard" connected={!pairing.presence?.online && records.some(record => record.id === pairing.id && record.presence?.online)} onClose={() => setPairing(null)} fail={fail} /></section>
  if (adding || !listed.length) return <section className="st-add-device" aria-label="Add a guard">
    <span className="st-device-icon"><ShieldCheck aria-hidden size={30} /></span><h2>{listed.length ? 'Add a guard' : 'Connect your team.'}</h2><p className="cm-muted">Enter their name, then scan the QR with their phone.</p>
    <form className="st-form" onSubmit={event => void addGuard(event)} onInvalidCapture={event => { const details = (event.target as HTMLElement).closest('details'); if (details) details.open = true }}>
      <label><span>Guard name</span><input value={form.name} maxLength={60} required onChange={event => setForm({ ...form, name: event.target.value })} autoComplete="name" /></label>
      {mode === 'clerk' && <label><span>Guard email</span><input type="email" required value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label>}
      <details className="st-building"><summary>More details</summary>
        <label><span>Floor / area (optional)</span><input value={form.floorName} maxLength={60} onChange={event => setForm({ ...form, floorName: event.target.value })} placeholder="e.g. Ground floor" /></label>
        {mode === 'dev' && <label><span>Email (optional)</span><input type="email" value={form.email} onChange={event => setForm({ ...form, email: event.target.value })} /></label>}
        <label><span>Guard reference</span><input value={form.callsign} placeholder={nextCallsign} pattern="[Gg][0-9]{1,2}" maxLength={3} onChange={event => setForm({ ...form, callsign: event.target.value })} /></label>
      </details>
      <button className="cm-btn cm-btn--dark" disabled={busy || !nextCallsign || !form.name.trim() || (mode === 'clerk' && !form.email.trim())}>{busy ? 'Getting ready…' : 'Connect phone'}<ArrowRight aria-hidden /></button>
      {listed.length > 0 && <button type="button" className="cm-btn" onClick={() => setAdding(false)}>Cancel</button>}
    </form>
    <p className="st-quiet-note">Adding guards is optional. You can continue and do this later.</p>
    {teamAccess}
  </section>
  return <section className="st-devices" aria-label="Your guards">
    <button type="button" className="cm-btn cm-btn--dark st-add-trigger" onClick={() => setAdding(true)}><Plus aria-hidden /> Add guard</button>
    <div className="st-device-list">{listed.map(record => <article key={record.id} className="st-device-row">
      <div className="st-device-heading"><span className="st-device-icon"><ShieldCheck aria-hidden size={24} /></span><div><h2>{record.name}</h2><p>{record.floorName || 'Floor not set'} · {record.presence?.online && record.shift === 'on_shift' ? 'On shift' : record.shift === 'break' ? 'On break' : 'Off shift'}</p></div><button type="button" className="cm-btn" disabled={busy} onClick={() => setPairing(record)}>Connect phone</button><button type="button" className="cm-btn st-remove-camera" disabled={busy} aria-label={`Remove ${record.name}`} onClick={() => void removeGuard(record)}>Remove</button></div>
      <details className="st-device-details"><summary>Details</summary>
        <form key={`${record.id}-${record.name}-${record.floorName}`} className="st-form" onSubmit={event => {
          event.preventDefault()
          if (busy) return
          setBusy(true)
          const data = new FormData(event.currentTarget)
          void api(`/guards/${record.id}`, 'PATCH', { name: String(data.get('name')).trim(), floorName: String(data.get('floorName') ?? '').trim() || null }).then(() => ok('Guard details saved.'), fail).finally(() => setBusy(false))
        }}>
          <label><span>Guard name</span><input name="name" defaultValue={record.name} required maxLength={60} /></label><label><span>Floor / area</span><input name="floorName" defaultValue={record.floorName ?? ''} maxLength={60} /></label><button className="cm-btn" disabled={busy}>Save guard details</button>
        </form>
        <p className="st-quiet-note">Reference: {record.callsign}{record.email ? ` · ${record.email}` : ''}</p>
        <p className="st-quiet-note">Their location is shared while they are on shift.</p>
      </details>
    </article>)}</div>
    {teamAccess}
  </section>
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
      ok('Test incident sent. Camera wall to review it.')
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
              Camera wall
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
