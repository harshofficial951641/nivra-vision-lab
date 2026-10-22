import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { api, socketUrl, type Incident } from '../classroom/contracts'
import { authenticateSocket } from '../auth/session'
import { sampleStore } from '../command/sampleStore'
import { CAMERA_SLOTS, PLAN, SAMPLE_FLOOR, SAMPLE_GUARDS, mapFloor } from '../command/siteMap'
import type { GuardAction } from '../command/model'
import type { FloorRecord, GuardRecord, MapFloor, Placement } from '../command/types'

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
> & { placement?: Placement | null; floorId?: string | null }

export interface GuardView {
  callsign: string
  name: string
  shift: GuardRecord['shift']
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
    let stopped = false
    let socket: WebSocket | null = null
    let timer = 0
    let attempts = 0
    const connect = () => {
      setConnection('connecting')
      socket = new WebSocket(socketUrl('/guard/stream'))
      authenticateSocket(socket)
      socket.onopen = () => {
        attempts = 0
        setConnection('connected')
        setProblem('')
      }
      socket.onmessage = (message) => {
        try {
          const data = JSON.parse(message.data)
          if (data?.type !== 'guard-snapshot' || !Array.isArray(data.alerts)) return
          setLiveAlerts(data.alerts)
          if (data.guard && typeof data.guard === 'object') setLiveGuard(data.guard)
          setLiveFloor(data.floor ?? null)
        } catch {
          // The next snapshot replaces state.
        }
      }
      socket.onclose = (event) => {
        if (stopped) return
        setConnection('disconnected')
        if (event.code === 4403) {
          setProblem('This account is not linked to a guard yet. Ask an admin to add you in Setup → Guards.')
          return
        }
        if (event.code === 4401) setProblem('Your sign-in expired. Reconnecting…')
        timer = window.setTimeout(connect, Math.min(10_000, 1000 * 2 ** Math.min(attempts++, 3)))
      }
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      socket?.close()
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

  return { view, alerts, connection, problem, act, setShift }
}

/** Register this phone for Web Push (contract §6). Returns a user-facing status. */
export async function enablePush(): Promise<'on' | 'denied' | 'unsupported' | 'install' | 'error'> {
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
