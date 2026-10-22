import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { api, openSocket, type Incident } from '../classroom/contracts'
import { authenticateSocket } from '../auth/session'
import { sampleStore } from '../command/sampleStore'
import { CAMERA_SLOTS, PLAN, SAMPLE_FLOOR, SAMPLE_GUARDS, mapFloor } from '../command/siteMap'
import type { GuardAction } from '../command/model'
import type { FloorRecord, GuardRecord, MapFloor, Placement } from '../command/types'
import type { GPSLocation } from '../location/gps'

/** Fields the service sends to a guard phone (contract §6). */
export type GuardAlert = Pick<
  Incident,
  | 'id'
  | 'camera_id'
  | 'camera_name'
  | 'location'
  | 'detail'
  | 'note'
  | 'received_at'
  | 'alerted_at'
  | 'guard_ack_at'
  | 'guard_declined_at'
  | 'on_scene_at'
  | 'status'
  | 'revision'
  | 'police'
> & { gps?: Incident['gps']; placement?: Placement | null; floorId?: string | null }

export interface GuardView {
  callsign: string
  name: string
  shift: GuardRecord['shift']
  gps?: GPSLocation | null
  floorName?: string | null
  /** Post in plan units of `floor`. */
  post: { x: number; y: number } | null
  floor: MapFloor | null
}

const noop = () => () => {}
const empty = () => null

function sampleView(callsign: string | null): GuardView | null {
  const guard = SAMPLE_GUARDS.find((g) => g.id === callsign)
  if (!guard) return null
  return {
    callsign: guard.id,
    name: guard.name,
    shift: guard.status === 'available' ? 'on_shift' : guard.status === 'break' ? 'break' : 'off',
    post: guard.x != null && guard.y != null ? { x: guard.x, y: guard.y } : null,
    floor: SAMPLE_FLOOR,
  }
}

/** Sample alerts carry the sample camera geometry as a normalized placement. */
function samplePlacement(cameraId: string): Placement | null {
  const slot = CAMERA_SLOTS.find((s) => s.id === cameraId)
  return slot
    ? { floorId: 'sample', x: slot.x / PLAN.width, y: slot.y / PLAN.height, angle: slot.angle, fov: slot.fov, range: slot.range / PLAN.width }
    : null
}

// A QR token is single-use. Share the exchange across StrictMode's effect replay.
let pairingRequest: Promise<unknown> | null = null
let pairingToken: string | null = null
function guardSession(signal?: AbortSignal) {
  let token = new URLSearchParams(location.hash.slice(1)).get('pair')
  try {
    const pending = JSON.parse(sessionStorage.getItem('nivra.guard.pendingPair') ?? 'null')
    if (!token && pending && Number.isFinite(pending.expiresAt) && pending.expiresAt > Date.now()) token = pending.token
    sessionStorage.removeItem('nivra.guard.pendingPair')
  } catch { /* Storage may be unavailable. Direct QR pairing still works. */ }
  if (token) {
    if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{30,100}$/.test(token)) return Promise.reject(new Error('This guard pairing link is invalid. Ask Command for a new QR code.'))
    if (!pairingRequest || token !== pairingToken) {
      history.replaceState(null, '', location.pathname + location.search)
      pairingToken = token
      const request = api('/guard/pair', 'POST', { token }, { timeoutMs: 10000 })
      pairingRequest = request
      const release = () => { if (pairingRequest === request) { pairingRequest = null; pairingToken = null } }
      void request.then(release, release)
    }
    return pairingRequest
  }
  return pairingRequest ?? api('/guard/session', 'GET', undefined, { signal })
}

export function useGuard(sample: boolean, sampleCallsign: string | null) {
  const store = sample ? sampleStore() : null
  const state = useSyncExternalStore(store?.subscribe ?? noop, store?.getState ?? empty)
  const [liveAlerts, setLiveAlerts] = useState<GuardAlert[]>([])
  const [liveGuard, setLiveGuard] = useState<GuardRecord | null>(null)
  const [liveFloor, setLiveFloor] = useState<FloorRecord | null>(null)
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'disconnected'>(
    sample ? 'connected' : 'connecting',
  )
  const [problem, setProblem] = useState('')
  const [sampleShift, setSampleShift] = useState<GuardRecord['shift'] | null>(null)

  useEffect(() => {
    if (sample) return
    let stopped = false, epoch = 0, attempts = 0, timer = 0, deadline = 0, heartbeat = 0
    let socket: WebSocket | null = null
    let lastSnapshot = -Infinity
    let attemptAbort: AbortController | null = null
    const detach = () => {
      const previous = socket; socket = null
      if (previous) { previous.onclose = null; previous.onmessage = null; previous.onerror = null; previous.onopen = null; previous.close() }
    }
    const retry = () => {
      epoch++
      attemptAbort?.abort()
      clearTimeout(deadline); clearInterval(heartbeat); heartbeat = 0; clearTimeout(timer)
      detach()
      setConnection('disconnected')
      timer = window.setTimeout(() => void connect(), Math.min(10000, 1000 * 2 ** Math.min(attempts++, 3)))
    }
    const connect = async () => {
      const current = ++epoch
      lastSnapshot = -Infinity
      setConnection('connecting')
      attemptAbort?.abort()
      const attempt = new AbortController()
      attemptAbort = attempt
      try {
        await guardSession(attempt.signal)
        if (stopped || current !== epoch) return
        const peer = await openSocket('/guard/stream', { signal: attempt.signal })
        if (stopped || current !== epoch) { peer.close(); return }
        socket = peer
        deadline = window.setTimeout(() => {
          if (!stopped && current === epoch) { setProblem('Connection timed out. Retrying…'); retry() }
        }, 12000)
        authenticateSocket(peer)
        peer.onopen = () => { /* Wait for an authenticated guard snapshot. */ }
        peer.onmessage = message => {
          if (stopped || current !== epoch || socket !== peer) return
          try {
            const data = JSON.parse(message.data)
            if (data?.type !== 'guard-snapshot' || !Array.isArray(data.alerts) || !data.guard ||
              typeof data.guard.callsign !== 'string' || typeof data.guard.name !== 'string' ||
              !['on_shift', 'break', 'off'].includes(data.guard.shift)) throw new Error('Invalid guard response')
            clearTimeout(deadline)
            lastSnapshot = Date.now()
            attempts = 0
            setConnection('connected'); setProblem('')
            setLiveAlerts(data.alerts); setLiveGuard(data.guard); setLiveFloor(data.floor ?? null)
            if (!heartbeat) heartbeat = window.setInterval(() => {
              if (stopped || current !== epoch || socket !== peer) return
              if (Date.now() - lastSnapshot > 25000) { setProblem('Connection interrupted. Retrying…'); retry(); return }
              if (peer.readyState === 1) peer.send('ping')
            }, 5000)
          } catch { setProblem('Could not read the guard update. Reconnecting…'); retry() }
        }
        peer.onerror = () => {
          if (stopped || current !== epoch || socket !== peer) return
          setProblem('Connection interrupted. Retrying…'); retry()
        }
        peer.onclose = event => {
          if (stopped || current !== epoch || socket !== peer) return
          if (event.code === 4403 || event.code === 4401) {
            epoch++; attemptAbort?.abort(); clearTimeout(deadline); clearInterval(heartbeat); heartbeat = 0
            socket = null
            setLiveGuard(null); setLiveAlerts([]); setLiveFloor(null)
            setConnection('disconnected')
            setProblem(event.code === 4403 ? 'This phone is not linked to a guard. Ask your owner for a new QR or code.' : 'Your sign-in expired. Sign in again.')
            return
          }
          setProblem('Connection lost. Retrying…'); retry()
        }
      } catch (reason) {
        if (stopped || current !== epoch) return
        setProblem(reason instanceof Error ? reason.message : 'Could not connect this guard phone.')
        if (reason && typeof reason === 'object' && 'status' in reason && [401, 403].includes(Number(reason.status))) {
          attemptAbort?.abort(); clearTimeout(deadline); setLiveGuard(null); setLiveAlerts([]); setLiveFloor(null); setConnection('disconnected')
          return
        }
        retry()
      }
    }
    const resume = () => {
      if (stopped || document.visibilityState === 'hidden') return
      if (socket?.readyState === 1 && Date.now() - lastSnapshot < 15000) return
      clearTimeout(timer); clearTimeout(deadline); clearInterval(heartbeat); heartbeat = 0
      epoch++; attemptAbort?.abort(); detach(); void connect()
    }
    window.addEventListener('online', resume)
    document.addEventListener('visibilitychange', resume)
    void connect()
    return () => {
      stopped = true; epoch++
      attemptAbort?.abort()
      clearTimeout(timer); clearTimeout(deadline); clearInterval(heartbeat)
      window.removeEventListener('online', resume)
      document.removeEventListener('visibilitychange', resume)
      detach()
    }
  }, [sample])

  const view = useMemo<GuardView | null>(() => {
    if (sample) {
      const base = sampleView(sampleCallsign)
      return base && sampleShift ? { ...base, shift: sampleShift } : base
    }
    if (!liveGuard) return null
    const floor = liveFloor ? mapFloor(liveFloor) : null
    return {
      callsign: liveGuard.callsign,
      name: liveGuard.name,
      shift: liveGuard.shift,
      gps: liveGuard.gps,
      floorName: liveGuard.floorName,
      post: liveGuard.post && floor ? { x: liveGuard.post.x * floor.width, y: liveGuard.post.y * floor.height } : null,
      floor,
    }
  }, [sample, sampleCallsign, sampleShift, liveGuard, liveFloor])

  const alerts = useMemo<GuardAlert[]>(() => {
    if (!sample) return liveAlerts
    if (!sampleCallsign) return []
    const cutoff = Date.now() - 30 * 60_000
    return (state?.events ?? [])
      .filter(
        (e) =>
          e.guard === sampleCallsign &&
          e.decision === 'confirmed' &&
          e.alerted_at &&
          (e.status !== 'resolved' || e.updated_at > cutoff),
      )
      .sort((a, b) => (b.alerted_at ?? 0) - (a.alerted_at ?? 0))
      .slice(0, 10)
      .map((e) => ({ ...e, placement: samplePlacement(e.camera_id), floorId: 'sample' }))
  }, [sample, liveAlerts, state, sampleCallsign])

  const act = useCallback(
    async (alert: GuardAlert, action: GuardAction) => {
      if (store) {
        store.guardAction(alert.id, action)
        return
      }
      const updated = await api<GuardAlert>(`/guard/events/${alert.id}`, 'POST', { action, revision: alert.revision })
      setLiveAlerts((list) => list.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)))
    },
    [store],
  )

  const setShift = useCallback(
    async (shift: GuardRecord['shift']) => {
      if (sample) {
        setSampleShift(shift)
        return
      }
      const updated = await api<GuardRecord>('/guard/shift', 'POST', { shift })
      setLiveGuard((old) => (old ? { ...old, ...updated } : updated))
    },
    [sample],
  )

  const saveGPS = useCallback(async (point: GPSLocation) => {
    if (sample) return
    const updated = await api<GuardRecord>('/guard/location', 'POST', point)
    setLiveGuard(old => old ? { ...old, ...updated } : updated)
  }, [sample])
  const saveFloor = useCallback(async (floorName: string | null) => {
    if (sample) return
    const updated = await api<GuardRecord>('/guard/profile', 'PATCH', { floorName })
    setLiveGuard(old => old ? { ...old, ...updated } : updated)
  }, [sample])

  return { view, alerts, connection, problem, act, setShift, saveGPS, saveFloor }
}

/** Register this phone for Web Push (contract §6). Returns a user-facing status. */
export async function enablePush(): Promise<'on' | 'denied' | 'unsupported' | 'install' | 'error'> {
  if (navigator.userAgent.includes('NIVRA-Native')) return 'unsupported'
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    const iOS = /iPhone|iPad|iPod/.test(navigator.userAgent)
    return iOS ? 'install' : 'unsupported'
  }
  try {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return 'denied'
    const registration = await navigator.serviceWorker.register('/guard-sw.js', { scope: '/guard' })
    await navigator.serviceWorker.ready
    const { publicKey } = await api<{ publicKey: string }>('/guard/push/key')
    const existing = await registration.pushManager.getSubscription()
    const subscription =
      existing ??
      (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(publicKey) }))
    await api('/guard/push', 'POST', { subscription: subscription.toJSON() })
    return 'on'
  } catch {
    return 'error'
  }
}

function urlBase64ToUint8Array(value: string) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const raw = atob((value + padding).replace(/-/g, '+').replace(/_/g, '/'))
  const output = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i)
  return output
}
