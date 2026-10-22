import type { CameraPose } from './skeletonGeometry'
import { DEVICE_PEOPLE_LIMIT } from './capacity'
import type { GPSLocation } from '../location/gps'
import { sessionToken } from '../auth/session'
import type { FloorRecord, GuardRecord, Placement } from '../command/types'
export const isLocalDashboard = ['localhost', '127.0.0.1'].includes(location.hostname)
export interface CameraLocation {
  gps?: GPSLocation | null
  id: string
  name: string
  label?: string | null
  placement?: Placement | null
  building: string
  floor: string
  enabled: boolean
  paired?: boolean
  feed: 'live' | 'waiting' | 'offline' | 'paused'
  analysis: 'current' | 'waiting' | 'unavailable' | 'paused'
  generation: string | null
  framesReceived: number
  framesAnalyzed: number
  framesReplaced: number
  compute?: 'device' | 'pc' | 'native' | null
  deviceStatus?: { state: 'loading' | 'ready' | 'error'; delegate: 'GPU' | 'CPU' | 'iOS' | null; detail: string } | null
  error?: string | null
  motionResult?: CameraLocation['result']
  motionStatus?: CameraLocation['deviceStatus']
  result?: {
    backend?: 'camera-device' | 'local-ai'
    delegate?: 'GPU' | 'CPU' | 'iOS'
    timestampMs: number
    inferenceMs: number
    evidenceTimestampMs: number
    coverage?: {
      observedPeople: number
      analyzedPeople: number
      excludedPeople: number
      status: string
      actionPeople: number
    }
    poses?: CameraPose[]
    tracks?: {
      id: number
      box: number[]
      ambiguous: boolean
      observed: boolean
    }[]
    conflict?: { status: string; explanation: string }
  } | null
}
export interface Incident {
  gps?: GPSLocation | null
  id: string
  camera_id: string
  camera_name: string
  location: string
  received_at: number
  source_ms: number
  evidence_ms: number
  model: string
  detail: string
  status: 'open' | 'acknowledged' | 'resolved'
  revision: number
  updated_at: number
  // Review lifecycle (schema v2+). Absent on older services.
  reviewed_at?: number | null
  decision?: 'confirmed' | 'false_alarm' | null
  reason?: 'play_sport' | 'greeting' | 'camera_glitch' | 'other' | null
  note?: string | null
  guard?: string | null
  decided_at?: number | null
  alerted_at?: number | null
  guard_ack_at?: number | null
  guard_declined_at?: number | null
  on_scene_at?: number | null
  escalated_at?: number | null
  reviewer_id?: string | null
  floor_id?: string | null
  clip?: { status: 'recording' | 'ready' | 'expired' | 'none'; frames: number } | null
}
export interface Snapshot {
  version: 2 | 3
  type: 'snapshot'
  cameras: CameraLocation[]
  events: Incident[]
  analytics: { total: number; pending: number; resolved: number; confirmed?: number; falseAlarms?: number }
  service: 'ready' | 'loading' | 'error'
  publicOrigin: string | null
  retention: 'event-records-only'
  experimental: true
  // v3 (command system). Absent on older services.
  serverTime?: number
  me?: { role: string } | null
  site?: { id: string; name: string } | null
  floors?: FloorRecord[]
  guards?: GuardRecord[]
  runtime: {
    compute?: 'camera-device'
    personModel?: string
    fightModel?: string
    maxPeople?: number
  } | null
}
export class ApiError extends Error {
  status: number
  detail?: unknown
  constructor(message: string, status: number, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}
export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  const token = await sessionToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? (method === 'GET' || path.endsWith('/socket-ticket') ? 12000 : 0)
  let timedOut = false
  const cancel = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) cancel()
  else options.signal?.addEventListener('abort', cancel, { once: true })
  const deadline = timeoutMs > 0 ? setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs) : undefined
  try {
  const response = await fetch(`/api/v2${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    signal: controller.signal,
    ...(method === 'GET' ? { cache: 'no-store' as const } : {}),
    body: body ? (isForm ? (body as FormData) : JSON.stringify(body)) : undefined,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(
      typeof payload?.detail === 'string'
        ? payload.detail
        : typeof payload?.detail?.message === 'string' ? payload.detail.message : `Request failed (${response.status}).`,
      response.status,
      payload?.detail,
    )
  }
  return response.status === 204 ? (undefined as T) : await response.json()
  } catch (reason) {
    if (timedOut) throw new Error('Connection is taking too long. Please try again.')
    throw reason
  } finally {
    clearTimeout(deadline)
    options.signal?.removeEventListener('abort', cancel)
  }
}
export function socketUrl(path: string) {
  return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v2${path}`
}
/** Public static hosting uses one-use socket tickets. Cookies remain on the API origin. */
export async function openSocket(path: string): Promise<WebSocket> {
  if (import.meta.env.VITE_NIVRA_DIRECT_SOCKET_RELAY !== '1') return new WebSocket(socketUrl(path))
  const endpoints: Record<string, string> = {
    '/operator': '/operator/socket-ticket',
    '/camera/stream': '/camera/socket-ticket',
    '/guard/stream': '/guard/socket-ticket',
  }
  const endpoint = endpoints[path]
  if (!endpoint) throw new Error('Unsupported socket destination.')
  const result = await api<{ url: string; ticket: string }>(endpoint, 'POST', {})
  let url: URL
  try { url = new URL(result.url) } catch { throw new Error('Invalid socket relay response.') }
  if (url.protocol !== 'wss:' || url.pathname !== `/api/v2${path}` || url.search || url.hash ||
    url.username || url.password || typeof result.ticket !== 'string' || !/^[A-Za-z0-9_-]{16,256}$/.test(result.ticket))
    throw new Error('Invalid socket relay response.')
  return new WebSocket(url.href, [`nivra-ticket.${result.ticket}`])
}

export async function framePacket(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  timestamp: number,
  longestSide = 960,
): Promise<ArrayBuffer | null> {
  if (!video.videoWidth || video.readyState < 2) return null
  const scale = Math.min(1, longestSide / Math.max(video.videoWidth, video.videoHeight))
  const width = Math.round(video.videoWidth * scale), height = Math.round(video.videoHeight * scale)
  if (canvas.width !== width) canvas.width = width
  if (canvas.height !== height) canvas.height = height
  const context = canvas.getContext('2d', { alpha: false })
  if (!context) return null
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  const jpeg = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.72),
  )
  if (!jpeg) return null
  const header = new TextEncoder().encode(
    JSON.stringify({
      version: 1,
      timestampMs: timestamp,
      streamId: 0,
      maxPeople: DEVICE_PEOPLE_LIMIT,
    }),
  )
  const packet = new Uint8Array(4 + header.length + jpeg.size)
  new DataView(packet.buffer).setUint32(0, header.length, true)
  packet.set(header, 4)
  packet.set(new Uint8Array(await jpeg.arrayBuffer()), 4 + header.length)
  return packet.buffer
}
