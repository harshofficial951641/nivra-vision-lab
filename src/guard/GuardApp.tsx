import { useEffect, useRef, useState } from 'react'
import { Bell, CheckCircle, WarningCircle } from '@phosphor-icons/react'
import { useOptionalSession } from '../auth/context'
import { GoogleMap } from '../location/GoogleMap'
import { googleMapsURL, validGPS } from '../location/gps'
import { useLiveGPS } from '../location/useLiveGPS'
import { formatElapsed, type GuardAction } from '../command/model'
import { SAMPLE_GUARDS } from '../command/siteMap'
import { RING_MS, RingPlayer, shouldRing } from './ringPlayer'
import { enablePush, useGuard, type GuardAlert } from './useGuard'
import '../command/command.css'
import { Brand } from '../ui/Brand'
import './guard.css'

const ringing = (a: GuardAlert) =>
  a.status !== 'resolved' && !!a.alerted_at && !a.guard_ack_at && !a.guard_declined_at

function useClock() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  return now
}

function useWakeLock(enabled: boolean) {
  const [held, setHeld] = useState(false)
  useEffect(() => {
    if (!enabled || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let active = true
    const request = async () => {
      try {
        lock = await navigator.wakeLock.request('screen')
        if (!active) return void lock.release()
        setHeld(true)
        lock.addEventListener('release', () => setHeld(false))
      } catch {
        setHeld(false)
      }
    }
    const onVisible = () => {
      if (document.visibilityState === 'visible') void request()
    }
    void request()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      active = false
      document.removeEventListener('visibilitychange', onVisible)
      void lock?.release()
    }
  }, [enabled])
  return held
}

function SlideToAcknowledge({ onDone, disabled }: { onDone: () => Promise<boolean>; disabled: boolean }) {
  const [value, setValue] = useState(0)
  const done = useRef(false)
  const finish = (next: number) => {
    setValue(next)
    if (next >= 92 && !done.current) {
      done.current = true
      void onDone().then(success => {
        if (!success) {
          done.current = false
          setValue(0)
        }
      })
    }
  }
  return (
    <label className="gd-slide" style={{ ['--slide' as string]: String(value) }}>
      <span className="gd-slide-text" aria-hidden>
        Slide to acknowledge
      </span>
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        disabled={disabled}
        aria-label="Slide to acknowledge the alert"
        onChange={(e) => finish(Number(e.target.value))}
        onPointerUp={() => {
          if (!done.current) setValue(0)
        }}
        onKeyUp={(e) => {
          if (e.key === 'Enter' || e.key === ' ') finish(100)
        }}
      />
    </label>
  )
}

export default function GuardApp() {
  const params = new URLSearchParams(location.search)
  const sample = params.get('demo') === '1'
  const nativeApp = navigator.userAgent.includes('NIVRA-Native')
  const sampleGuard = /^G[0-9]{1,2}$/.test(params.get('guard') ?? '') ? params.get('guard') : null
  const session = useOptionalSession()
  const { view, alerts, connection, problem, act, setShift, saveGPS, saveFloor } = useGuard(sample, sampleGuard)
  const now = useClock()
  const [started, setStarted] = useState(false)
  const [startingShift, setStartingShift] = useState(false)
  const [audio, setAudio] = useState<'ok' | 'blocked' | null>(null)
  const [push, setPush] = useState<'on' | 'denied' | 'unsupported' | 'install' | 'error' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const player = useRef<RingPlayer | null>(null)
  const rings = useRef(new Map<string, { count: number; last: number; alertedAt: number }>())
  const awake = useWakeLock(started)
  const tracking = started && view?.shift === 'on_shift' && !sample
  const gps = useLiveGPS(tracking, saveGPS)
  const [floorName, setFloorName] = useState('')
  const [floorBusy, setFloorBusy] = useState(false)
  useEffect(() => { setFloorName(view?.floorName ?? '') }, [view?.floorName])
  const updateFloor = async () => {
    if (floorBusy || !floorName.trim()) return
    setFloorBusy(true)
    setError('')
    try { await saveFloor(floorName.trim() || null) }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save your floor.') }
    finally { setFloorBusy(false) }
  }
  const ownLocation = (
    <section className="gd-location" aria-label="Your live location">
      <p>{view?.name} · {view?.callsign}{view?.floorName ? ` · ${view.floorName}` : ''}</p>
      <p role="status">{sample ? 'Sample guard. Live GPS is off.' : tracking
        ? gps.point ? `Live GPS · shared ${gps.age}s ago · accuracy ±${Math.ceil(gps.point.accuracy)} m` : 'Getting your live GPS location…'
        : started ? 'Location is paused. Choose On shift to share it.' : 'Location is paused. Tap Start shift to share it.'}</p>
      {tracking && gps.error && <><p role="alert">{gps.error}</p><button type="button" className="gd-text-btn" onClick={gps.retry}>Retry GPS location</button></>}
      {!sample && <details className="gd-tools"><summary>Change floor</summary><form onSubmit={event => { event.preventDefault(); void updateFloor() }}>
        <label htmlFor="guard-floor">Current floor</label>
        <div><input id="guard-floor" required value={floorName} maxLength={60} placeholder="e.g. Ground floor" onChange={event => setFloorName(event.target.value)} />
          <button type="submit" disabled={floorBusy || !floorName.trim() || floorName.trim() === (view?.floorName ?? '')}>{floorBusy ? 'Saving…' : 'Save floor'}</button></div>
        <p>Set your floor yourself. GPS cannot tell which indoor floor you are on.</p>
      </form></details>}
    </section>
  )

  const incoming = alerts.find(ringing) ?? null
  const responding = alerts.find((a) => a.status !== 'resolved' && a.guard_ack_at) ?? null
  const last = alerts[0] ?? null

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [incoming?.id, responding?.id, started])

  useEffect(() => () => player.current?.dispose(), [])

  // Installable guard app (Add to Home Screen enables lock-screen alerts on iOS).
  useEffect(() => {
    const added: HTMLElement[] = []
    const add = (tag: string, attrs: Record<string, string>) => {
      const el = document.createElement(tag)
      Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v))
      document.head.appendChild(el)
      added.push(el)
    }
    add('link', { rel: 'manifest', href: '/guard.webmanifest' })
    add('link', { rel: 'apple-touch-icon', href: '/guard-icons/guard-192.png' })
    add('meta', { name: 'theme-color', content: '#0b0b0c' })
    add('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' })
    document.title = 'NIVRA Guard'
    return () => added.forEach((el) => el.remove())
  }, [])

  // Ring for new alerts, then every 15 s up to four times until answered.
  useEffect(() => {
    if (!started || !incoming?.alerted_at) {
      player.current?.stop()
      return
    }
    const record = rings.current.get(incoming.id)
    const state =
      record && record.alertedAt === incoming.alerted_at ? record : { count: 0, last: 0, alertedAt: incoming.alerted_at }
    if (shouldRing(incoming.alerted_at, state.count, state.last, Date.now())) {
      player.current?.ring(RING_MS)
      rings.current.set(incoming.id, { ...state, count: state.count + 1, last: Date.now() })
    } else rings.current.set(incoming.id, state)
  }, [started, incoming, now])

  const startShift = async () => {
    if (startingShift) return
    setStartingShift(true)
    setError('')
    try {
      player.current ??= new RingPlayer()
      const ok = await player.current.prime()
      setAudio(ok ? 'ok' : 'blocked')
      if (view?.shift !== 'on_shift') await setShift('on_shift')
      setStarted(true)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not start your shift. Try again.') }
    finally { setStartingShift(false) }
  }
  const testRing = async () => {
    player.current ??= new RingPlayer()
    if (!player.current.ready) setAudio((await player.current.prime()) ? 'ok' : 'blocked')
    player.current.ring(RING_MS)
  }
  const run = async (alert: GuardAlert, action: GuardAction) => {
    setBusy(true)
    setError('')
    player.current?.stop()
    try {
      await act(alert, action)
      return true
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Update failed. Check the connection and try again.')
      return false
    } finally {
      setBusy(false)
    }
  }
  const changeShift = async (shift: 'on_shift' | 'break' | 'off') => {
    setError('')
    try {
      await setShift(shift)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update your shift.')
    }
  }
  const turnOnAlerts = async () => {
    if (sample) {
      setPush('unsupported')
      return
    }
    setPush(await enablePush())
  }


  if (sample && !sampleGuard)
    return (
      <main className="gd-app gd-dark gd-center">
        <div className="gd-brand"><Brand compact /><span>Guard</span></div>
        <h1>Choose a sample guard</h1>
        <p className="gd-muted">Sample workspace. Pick whose phone this tab is.</p>
        <div className="gd-guard-pick">
          {SAMPLE_GUARDS.map((g) => (
            <a key={g.id} className="gd-btn gd-btn--outline" href={`/guard?demo=1&guard=${g.id}`}>
              {g.id} · {g.name}
            </a>
          ))}
        </div>
      </main>
    )

  if (!sample && !view)
    return (
      <main className="gd-app gd-dark gd-center">
        <div className="gd-brand"><Brand compact /><span>Guard</span></div>
        <p role="status" className={problem ? 'gd-error' : 'gd-muted'}>
          {problem || (connection === 'connected' ? 'Loading your guard profile…' : 'Connecting to NIVRA…')}
        </p>
        {problem && <p className="gd-muted gd-small">Ask your team for a new guard QR and scan it. If your site uses accounts, sign in with the guard account assigned to you.</p>}
        {problem && <a className="gd-btn gd-btn--outline" href="/login?next=/guard">Sign in to NIVRA</a>}
        {problem && session && (
          <button type="button" className="gd-text-btn" onClick={() => void session.signOut()}>
            Sign out
          </button>
        )}
      </main>
    )


  if (incoming && started)
    return (
      <main className="gd-app gd-alert" aria-live="assertive">
        <div className="gd-bell" aria-hidden>
          <span />
          <span />
          <span />
          <Bell weight="bold" />
        </div>
        <h1>Go to {incoming.camera_name}</h1>
        <p className="gd-alert-what">
          Possible physical conflict{incoming.location ? ` · ${incoming.location}` : ''}
        </p>
        {incoming.note && <p className="gd-alert-note">“{incoming.note}”</p>}
        <p className="gd-alert-time">Alerted {formatElapsed(now - (incoming.alerted_at ?? now))} ago</p>
        {error && (
          <p className="gd-error" role="alert">
            {error}
          </p>
        )}
        <SlideToAcknowledge key={incoming.id} disabled={busy} onDone={() => run(incoming, 'ack')} />
        <button type="button" className="gd-text-btn" disabled={busy} onClick={() => void run(incoming, 'decline')}>
          Can’t respond
        </button>
      </main>
    )

  if (responding && started) {
    return (
      <main className="gd-app gd-dark gd-respond">
        <p className="gd-chip" role="status">
          {responding.on_scene_at
            ? `On scene · ${formatElapsed(now - responding.on_scene_at)}`
            : `Acknowledged · ${formatElapsed(now - (responding.guard_ack_at ?? now))}`}
        </p>
        <h1>Go to {responding.camera_name}</h1>
        <p className="gd-muted">{responding.location}</p>
        {ownLocation}
        <div className="gd-map"><GoogleMap point={responding.gps} label={responding.camera_name} sample={sample} /></div>
        {validGPS(responding.gps) && <a className="gd-btn gd-btn--light" href={googleMapsURL(responding.gps, true)} target="_blank" rel="noreferrer">Navigate with Google Maps ↗</a>}
        {responding.note && <p className="gd-note">{responding.note}</p>}
        {error && (
          <p className="gd-error" role="alert">
            {error}
          </p>
        )}
        <div className="gd-actions">
          {!responding.on_scene_at ? (
            <button type="button" className="gd-btn gd-btn--light" disabled={busy} onClick={() => void run(responding, 'on_scene')}>
              I’m on scene
            </button>
          ) : (
            <button type="button" className="gd-btn gd-btn--light" disabled={busy} onClick={() => void run(responding, 'clear')}>
              Situation clear
            </button>
          )}
          {!responding.on_scene_at && (
            <button type="button" className="gd-btn gd-btn--outline" disabled>
              Situation clear
            </button>
          )}
        </div>
        <p className="gd-muted gd-small">Your team sees your updates.</p>
      </main>
    )
  }

  const shift = view?.shift ?? 'off'
  return (
    <main className={`gd-app gd-dark gd-idle${started ? '' : ' gd-before-shift'}`}>
      <div className="gd-brand"><Brand compact /><span>Guard</span></div>
      <time className="gd-time">
        {new Date(now).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })}
      </time>
      <p className="gd-who">
        {view?.callsign} · {view?.name}
      </p>
      <p className="gd-muted" role="status">
        <span className={`gd-dot ${connection === 'connected' ? 'is-on' : ''}`} />
        {connection === 'connected' ? 'Connected to your team' : connection === 'connecting' ? 'Connecting…' : 'Connection lost · retrying'}
      </p>
      {ownLocation}
      {!started ? (
        <>
          <section className="gd-phone-setup" aria-label="Guard phone setup"><p>Start your shift to receive alerts.</p></section>
          <button type="button" className="gd-btn gd-btn--light gd-start" disabled={startingShift || connection !== 'connected'} onClick={() => void startShift()}>
            {startingShift ? 'Starting shift…' : 'Start shift'}
          </button>
          <p className="gd-muted gd-small">Allow location when asked. Keep this screen open.</p>
        </>
      ) : (
        <>
          <div className="gd-shift" role="radiogroup" aria-label="Shift status">
            {(
              [
                ['on_shift', 'On shift'],
                ['break', 'Break'],
                ['off', 'Off'],
              ] as const
            ).map(([value, text]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={shift === value}
                className={shift === value ? 'is-on' : ''}
                onClick={() => void changeShift(value)}
              >
                {text}
              </button>
            ))}
          </div>
          <details className="gd-tools"><summary>Sound and notifications</summary><div className="gd-row">
            <button type="button" className="gd-btn gd-btn--outline" onClick={() => void testRing()}>
              Test ring
            </button>
            {!nativeApp && push !== 'on' && push !== 'unsupported' && (
              <button type="button" className="gd-btn gd-btn--outline" onClick={() => void turnOnAlerts()}>
                Alerts when locked
              </button>
            )}
          </div>{nativeApp && <p>Keep this screen open to hear alerts. Lock-screen alerts are unavailable in this app.</p>}</details>
        </>
      )}
      {push && push !== 'on' && (
        <p className="gd-error" role="status">
          {push === 'install'
            ? 'On iPhone: tap Share → Add to Home Screen, open NIVRA Guard from there, then turn on alerts.'
            : push === 'denied'
              ? 'Notifications are blocked. Allow them for this site in your phone settings.'
              : push === 'unsupported'
                ? sample
                  ? 'Lock-screen alerts need the live service. Keep this tab open to hear the ring.'
                  : 'This browser can’t receive alerts while locked. Keep this screen open.'
                : 'Could not turn on lock-screen alerts. Keep this screen open and try again.'}
        </p>
      )}
      {push === 'on' && (
        <p className="gd-last">
          <CheckCircle aria-hidden /> Alerts arrive even when the phone is locked.
        </p>
      )}
      {audio === 'blocked' && (
        <p className="gd-error" role="alert">
          <WarningCircle aria-hidden /> Sound is blocked. Turn off silent mode, raise the volume and tap Test ring.
        </p>
      )}
      {error && (
        <p className="gd-error" role="alert">
          {error}
        </p>
      )}
      {incoming && !started && (
        <p className="gd-error" role="alert">
          An alert is waiting. Tap Start shift to see it.
        </p>
      )}
      {last && !incoming && !responding && (
        <p className="gd-last">
          <CheckCircle aria-hidden />
          {last.guard_declined_at
            ? `You couldn’t respond to the ${last.camera_name} alert. Command was told.`
            : `Last alert · ${last.camera_name} · ${last.status === 'resolved' ? 'cleared' : 'open'}`}
        </p>
      )}
      <footer className="gd-foot">
        {!sample && <a href="/guard?connect=1">Scan a new QR or code</a>}
        <span>
          {started
            ? awake
              ? 'Screen stays awake while on shift'
              : 'Keep this screen on. Your phone may lock it.'
            : 'Keep this page open during your shift'}
        </span>
        {session?.me && (
          <button type="button" className="gd-text-btn gd-small" onClick={() => void session.signOut()}>
            Sign out
          </button>
        )}
      </footer>
    </main>
  )
}
