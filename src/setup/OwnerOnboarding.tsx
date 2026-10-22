import { useEffect, useRef, useState, type FormEvent, type TouchEvent } from 'react'
import { ArrowRight, Check, SquaresFour } from '@phosphor-icons/react'
import { ApiError, api, type CameraLocation } from '../classroom/contracts'
import type { useClassroom } from '../classroom/useClassroom'
import { useSession } from '../auth/context'
import type { GuardRecord } from '../command/types'
import { gpsStatus, recentGPS } from '../command/model'
import { PairingPanel } from './PairingPanel'
import { Brand } from '../ui/Brand'
import './onboarding.css'

const steps = ['Your site', 'Camera phone', 'Guard phone', 'Launch the wall']
const errorText = (reason: unknown) => reason instanceof Error ? reason.message : 'Could not save. Try again.'
const initialStep = () => ({ site: 0, cameras: 1, guards: 2, launch: 3 }[location.hash.slice(1)] ?? 0)

export default function OwnerOnboarding({ live }: { live: ReturnType<typeof useClassroom> }) {
  const session = useSession()
  const snapshot = live.snapshot
  const [step, setStep] = useState(initialStep)
  const [furthest, setFurthest] = useState(initialStep)
  const touch = useRef<{ x: number; y: number; at: number } | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer) }, [])
  useEffect(() => { heading.current?.focus({ preventScroll: true }) }, [step])
  const [savedSite, setSavedSite] = useState<string | null>(null)
  const [createdCamera, setCreatedCamera] = useState<CameraLocation | null>(null)
  const [createdGuard, setCreatedGuard] = useState<GuardRecord | null>(null)
  const [cameraId, setCameraId] = useState('')
  const [addingCamera, setAddingCamera] = useState(false)
  const [addingGuard, setAddingGuard] = useState(false)
  const [guardId, setGuardId] = useState('')
  const [cameraPair, setCameraPair] = useState<string | null>(null)
  const [guardPair, setGuardPair] = useState<string | null>(null)
  const [guardSkipped, setGuardSkipped] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (createdCamera && snapshot?.cameras.some(camera => camera.id === createdCamera.id)) setCreatedCamera(null)
    if (createdGuard && snapshot?.guards?.some(guard => guard.id === createdGuard.id)) setCreatedGuard(null)
  }, [snapshot, createdCamera, createdGuard])
  const cameras = [...(snapshot?.cameras ?? [])]
  if (createdCamera && !cameras.some(camera => camera.id === createdCamera.id)) cameras.push(createdCamera)
  const guards = [...(snapshot?.guards ?? [])]
  if (createdGuard && !guards.some(guard => guard.id === createdGuard.id)) guards.push(createdGuard)
  const camera = cameras.find(camera => camera.id === cameraId) ?? cameras[0]
  const guard = guards.find(guard => guard.id === guardId) ?? guards[0]
  const siteName = savedSite ?? snapshot?.site?.name ?? ''
  const unlocked = Math.max(furthest, siteName ? 1 : 0, camera ? 2 : 0, guard || guardSkipped ? 3 : 0)
  const go = (next: number, unlock = false) => {
    if (next < 0 || next > 3 || (!unlock && next > unlocked)) return
    if (unlock) setFurthest(current => Math.max(current, next))
    setError('')
    setStep(next)
    history.replaceState(null, '', `#${['site', 'cameras', 'guards', 'launch'][next]}`)
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }
  const swipeStart = (event: TouchEvent<HTMLElement>) => {
    const interactive = (event.target as HTMLElement).closest('button,a,input,select,textarea,label,details,summary,[contenteditable]')
    touch.current = event.touches.length === 1 && !interactive
      ? { x: event.touches[0].clientX, y: event.touches[0].clientY, at: Date.now() } : null
  }
  const swipeEnd = (event: TouchEvent<HTMLElement>) => {
    const start = touch.current; touch.current = null
    if (!start || event.changedTouches.length !== 1 || Date.now() - start.at > 600) return
    const dx = event.changedTouches[0].clientX - start.x
    const dy = event.changedTouches[0].clientY - start.y
    if (Math.abs(dx) >= 64 && Math.abs(dx) > Math.abs(dy) * 1.5) go(step + (dx < 0 ? 1 : -1))
  }
  const connected = live.connection === 'connected'
  const cameraLive = connected && camera?.feed === 'live'
  const guardLive = connected && guard?.shift === 'on_shift' && guard.presence?.online
  const complete = [!!siteName, !!cameraLive, !!guardLive, false]
  return <div className="ob-app st-app">
    <header className="ob-top"><a className="ob-brand" href="/mobile" aria-label="NIVRA home"><Brand compact /></a><span>Set up your site</span><span className="ob-connection" role="status">{connected ? 'Connected' : 'Reconnecting…'}</span><a href="/setup">Manage devices</a></header>
    <div className="ob-shell">
      <nav className="ob-steps" aria-label="First-run setup"><ol>{steps.map((label, index) => <li key={label}><button type="button" aria-label={`Step ${index + 1}: ${label}`} aria-current={step === index ? 'step' : undefined} disabled={index > unlocked} onClick={() => go(index)}><span className="ob-step-number" aria-hidden>{complete[index] ? <Check /> : index + 1}</span></button></li>)}</ol></nav>
      <main className="ob-main" aria-labelledby="ob-title" onTouchStart={swipeStart} onTouchEnd={swipeEnd} onTouchCancel={() => { touch.current = null }}>
        <header className="ob-heading"><span>Step {step + 1} of 4</span><h1 id="ob-title" ref={heading} tabIndex={-1}>{steps[step]}</h1><p>{['What should we call this place?', cameraPair ? 'Scan this code with the camera phone.' : 'A name and floor, then connect its phone.', guardPair ? 'Scan this code with the guard’s phone.' : 'Optional. Give a guard their own alerts.', 'Your phones will appear as they connect.'][step]}</p></header>
        {step !== 3 && !cameraPair && !guardPair && siteName && connected && cameras.some(item => item.feed === 'live') && <div className="ob-ready"><p>Your camera is ready.</p><a className="ob-primary" href="/wall">Open camera wall <ArrowRight aria-hidden /></a></div>}
        {(live.error || error) && <p className="ob-error" role="alert">{error || live.error}</p>}
        {!snapshot ? <p role="status">Connecting to the NIVRA service. Your saved setup will appear here.</p> : <>
          <section hidden={step !== 0} className="ob-stage" aria-label="Site setup">
            <SiteForm name={siteName} disabled={!connected} save={name => { setSavedSite(name); go(1, true) }} fail={setError} />
            <p className="ob-help">This browser keeps your owner access. Keep it on a device you trust.</p>
          </section>
          <section hidden={step !== 1 || !!cameraPair} className="ob-stage" aria-label="Camera setup">
            {(!cameras.length || addingCamera) ? <CameraForm siteName={siteName} disabled={!connected} save={record => { setCreatedCamera(record); setCameraId(record.id); setCameraPair(record.id); setAddingCamera(false) }} fail={setError} /> : <>
              {cameras.length > 1 && <div className="ob-picker"><span>Choose a camera</span><ul>{cameras.map(item => <li key={item.id}><button type="button" aria-pressed={camera?.id === item.id} onClick={() => setCameraId(item.id)}>{item.name}<small>{item.floor}</small></button></li>)}</ul></div>}
              <div className="ob-selected"><strong>{camera?.name}</strong><span>{camera?.floor}</span>{!cameraPair && <p role="status">{cameraLive ? 'Video is reaching the wall.' : 'Waiting for this phone to start its camera.'}</p>}</div>
              <button type="button" className="ob-primary" disabled={!connected || !camera?.enabled} onClick={() => setCameraPair(camera!.id)}>Connect phone <ArrowRight aria-hidden /></button>
              <button type="button" className="ob-text-action" onClick={() => setAddingCamera(true)}>Add another camera</button>
            </>}
          </section>
          <section hidden={step !== 2 || !!guardPair} className="ob-stage" aria-label="Guard setup">
            {(!guards.length || addingGuard) ? <GuardForm mode={session.mode} guards={guards} disabled={!connected} begin={() => setAddingGuard(true)} save={record => { setCreatedGuard(record); setGuardId(record.id); setGuardPair(record.callsign); setGuardSkipped(false); setAddingGuard(false) }} fail={setError} /> : <>
              {guards.length > 1 && <div className="ob-picker"><span>Choose a guard</span><ul>{guards.map(item => <li key={item.id}><button type="button" aria-pressed={guard?.id === item.id} onClick={() => setGuardId(item.id)}>{item.name}<small>{item.floorName || 'Floor not set'}</small></button></li>)}</ul></div>}
              <div className="ob-selected"><strong>{guard?.name}</strong><span>{guard?.floorName || 'Floor not set'}</span>{!guardPair && <p role="status">{guardLive ? 'Guard is online and on shift.' : 'Waiting for this guard to start their shift.'}</p>}</div>
              <button type="button" className="ob-primary" disabled={!connected || (session.mode === 'clerk' && !guard?.email)} onClick={() => setGuardPair(guard!.callsign)}>Connect phone <ArrowRight aria-hidden /></button>
              {session.mode === 'clerk' && !guard?.email && <p>Add their sign-in email in Manage devices first.</p>}
              <button type="button" className="ob-text-action" onClick={() => setAddingGuard(true)}>Add another guard</button>
            </>}
          </section>
          <section hidden={step !== 3} className="ob-launch" aria-label="Launch checklist">
            <SquaresFour aria-hidden size={28} /><h2>{siteName || 'Your site'} is saved.</h2><p>You can start watching now. Waiting phones will join when they connect.</p>
            <ul>{[
              { done: connected, label: connected ? 'Owner console connected' : 'Owner console disconnected' },
              { done: !!cameraLive && connected, label: camera ? `${camera.name} · ${cameraLive && connected ? 'video arriving' : 'waiting for video'}` : 'No camera added' },
              { done: !!camera && recentGPS(camera.gps, now) && connected, label: camera ? `${camera.name} · ${gpsStatus(camera.gps, now)}` : 'Camera GPS not available yet' },
              { done: !!guardLive && connected, label: guard ? `${guard.name} · ${guardLive && connected ? 'online and on shift' : 'waiting for shift'}` : 'Guard setup skipped. Incident dispatch needs a guard.' },
            ].map(check => <li key={check.label}><span aria-hidden>{check.done ? <Check /> : '○'}</span><span>{check.label}</span><small>{check.done ? 'Ready' : 'Pending'}</small></li>)}</ul>
            <details className="ob-verification"><summary>Owner access</summary><p>Owner verification can be added later. You can open your wall now.</p></details>

            <div className="ob-launch-actions"><a className="ob-primary" href="/wall">Open camera wall <ArrowRight aria-hidden /></a><a href="/setup#test">Run an optional test alert</a></div>
          </section>
          <div hidden={step !== 1 || !cameraPair} className="ob-pair-wrap">{cameraPair && <PairingPanel key={cameraPair} endpoint={`/cameras/${cameraPair}/pair`} kind="camera" label={cameras.find(camera => camera.id === cameraPair)?.name ?? 'Camera'} onClose={() => setCameraPair(null)} fail={reason => setError(errorText(reason))} />}{cameraPair && <p className="ob-pair-status" role="status">{cameraLive ? 'Video is reaching the wall.' : 'Waiting for this phone to start its camera.'}</p>}</div>
          <div hidden={step !== 2 || !guardPair} className="ob-pair-wrap">{guardPair && <PairingPanel key={guardPair} endpoint={`/guards/${guardPair}/pair`} kind="guard" label={guards.find(guard => guard.callsign === guardPair)?.name ?? 'Guard'} onClose={() => setGuardPair(null)} fail={reason => setError(errorText(reason))} />}{guardPair && <p className="ob-pair-status" role="status">{guardLive ? 'Guard is online and on shift.' : 'Waiting for this guard to start their shift.'}</p>}</div>
          <footer className="ob-foot"><button type="button" disabled={step === 0} onClick={() => go(step - 1)}>Back</button>{step === 1 && <button type="button" className={cameraPair ? "ob-primary" : undefined} disabled={!camera || !connected} onClick={() => go(2)}>Add a guard (optional) <ArrowRight aria-hidden /></button>}{step === 2 && <><button type="button" onClick={() => { setGuardSkipped(true); go(3, true) }}>Set up guards later</button><button type="button" className={guardPair ? "ob-primary" : undefined} disabled={!guard || !connected} onClick={() => go(3)}>Check and launch <ArrowRight aria-hidden /></button></>}</footer>
        </>}
      </main>
    </div>
  </div>
}

function SiteForm({ name, disabled, save, fail }: { name: string; disabled: boolean; save: (name: string) => void; fail: (error: string) => void }) {
  const [value, setValue] = useState(name)
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!value.trim() || busy || disabled) return
    setBusy(true)
    try { if (value.trim() !== name) await api('/site', 'PATCH', { name: value.trim() }); save(value.trim()) }
    catch (reason) { fail(errorText(reason)) }
    finally { setBusy(false) }
  }
  return <form className="ob-form" onSubmit={submit}><label htmlFor="ob-site-name">Site name</label><input id="ob-site-name" value={value} onChange={event => setValue(event.target.value)} required maxLength={60} placeholder="e.g. Main office" /><p className="ob-field-note">Shown on the camera wall and guard phones.</p><button type="submit" className="ob-primary" disabled={disabled || busy || !value.trim()}>{busy ? 'Saving…' : 'Save and continue'}<ArrowRight aria-hidden /></button></form>
}

function CameraForm({ siteName, disabled, save, fail }: { siteName: string; disabled: boolean; save: (camera: CameraLocation) => void; fail: (error: string) => void }) {
  const [name, setName] = useState(''), [building, setBuilding] = useState<string | null>(null), [floor, setFloor] = useState(''), [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (disabled || busy || !name.trim() || !(building ?? siteName).trim() || !floor.trim()) return
    setBusy(true)
    try { save(await api<CameraLocation>('/cameras', 'POST', { name: name.trim(), building: (building ?? siteName).trim(), floor: floor.trim() })); setName(''); setFloor('') }
    catch (reason) { fail(errorText(reason)) }
    finally { setBusy(false) }
  }
  return <form className="ob-form" onSubmit={submit}><label htmlFor="ob-camera-name">Camera name</label><input id="ob-camera-name" value={name} onChange={event => setName(event.target.value)} required maxLength={60} placeholder="e.g. Main entrance" /><label htmlFor="ob-camera-floor">Floor / area</label><input id="ob-camera-floor" value={floor} onChange={event => setFloor(event.target.value)} required maxLength={60} placeholder="e.g. Ground floor or Outside" /><details className="ob-details" onInvalidCapture={event => { event.currentTarget.open = true }}><summary>Change building / site</summary><label htmlFor="ob-building">Building / site</label><input id="ob-building" value={building ?? siteName} onChange={event => setBuilding(event.target.value)} required maxLength={60} /></details><button type="submit" className="ob-primary" disabled={disabled || busy || !name.trim() || !(building ?? siteName).trim() || !floor.trim()}>{busy ? 'Adding…' : 'Connect phone'}<ArrowRight aria-hidden /></button></form>
}

function GuardForm({ mode, guards, disabled, begin, save, fail }: { mode: 'dev' | 'clerk'; guards: GuardRecord[]; disabled: boolean; begin: () => void; save: (guard: GuardRecord) => void; fail: (error: string) => void }) {
  const [name, setName] = useState(''), [floorName, setFloor] = useState(''), [email, setEmail] = useState(''), [busy, setBusy] = useState(false)
  const [savedInvitation, setSavedInvitation] = useState<{ id: string; callsign: string; email: string } | null>(null)
  const callsign = Array.from({ length: 99 }, (_, index) => `G${index + 1}`).find(id => !guards.some(guard => guard.callsign === id))
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (disabled || busy || savedInvitation || !callsign || !name.trim() || !floorName.trim() || (mode === 'clerk' && !email.trim())) return
    begin()
    setBusy(true)
    try { save(await api<GuardRecord>('/guards', 'POST', { callsign, name: name.trim(), floorName: floorName.trim(), ...(email.trim() ? { email: email.trim().toLowerCase() } : {}) })); setName(''); setFloor(''); setEmail('') }
    catch (reason) {
      if (reason instanceof ApiError && reason.status === 502 && reason.detail && typeof reason.detail === 'object' && 'guardId' in reason.detail && typeof reason.detail.guardId === 'string') {
        setSavedInvitation({ id: reason.detail.guardId, callsign, email: email.trim().toLowerCase() })
        fail('The guard was saved, but the account invitation failed. Retry the invitation below. Do not add the guard again.')
      } else fail(errorText(reason))
    }
    finally { setBusy(false) }
  }
  const retryInvitation = async () => {
    if (!savedInvitation || busy || disabled) return
    setBusy(true)
    try {
      await api('/members/invite', 'POST', { email: savedInvitation.email, role: 'guard', callsign: savedInvitation.callsign })
      const records = await api<GuardRecord[]>('/guards')
      const saved = records.find(record => record.id === savedInvitation.id)
      if (!saved) throw new Error('Invitation sent, but the saved guard could not be refreshed. Open Manage devices.')
      save(saved)
      setSavedInvitation(null); setName(''); setFloor(''); setEmail(''); fail('')
    } catch (reason) { fail(errorText(reason)) }
    finally { setBusy(false) }
  }
  return <form className="ob-form" onSubmit={submit}>{savedInvitation && <div className="ob-invite-retry"><p>The guard record is saved. Only the account invitation needs another attempt.</p><button type="button" disabled={busy || disabled} onClick={() => void retryInvitation()}>{busy ? 'Retrying…' : 'Retry guard invitation'}</button><a href="/setup#guards">Manage this guard</a></div>}<label htmlFor="ob-guard-name">Guard name</label><input id="ob-guard-name" value={name} onChange={event => setName(event.target.value)} required maxLength={60} placeholder="e.g. Asha Sharma" /><label htmlFor="ob-guard-floor">Current floor / area</label><input id="ob-guard-floor" value={floorName} onChange={event => setFloor(event.target.value)} required maxLength={60} placeholder="e.g. Floor 2" />{mode === 'clerk' ? <><label htmlFor="ob-guard-email">Email (required for sign-in)</label><input id="ob-guard-email" type="email" value={email} onChange={event => setEmail(event.target.value)} required /></> : <details className="ob-details"><summary>Add an email (optional)</summary><label htmlFor="ob-guard-email">Email (optional)</label><input id="ob-guard-email" type="email" value={email} onChange={event => setEmail(event.target.value)} /></details>}<p className="ob-field-note">{!callsign ? 'All guard spaces are in use.' : mode === 'clerk' ? 'We’ll email their sign-in invitation.' : 'Next, scan the code with their phone.'}</p><button type="submit" className="ob-primary" disabled={disabled || busy || !!savedInvitation || !callsign || !name.trim() || !floorName.trim() || (mode === 'clerk' && !email.trim())}>{busy ? 'Adding…' : 'Connect phone'}<ArrowRight aria-hidden /></button></form>
}
