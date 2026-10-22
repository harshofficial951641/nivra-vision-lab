import { sessionToken } from '../auth/session'
import type { FloorRecord, GuardRecord, Placement } from '../command/types'
export const isLocalDashboard = ['localhost', '127.0.0.1'].includes(location.hostname)
export interface CameraLocation {
  id: string
  name: string
  label?: string | null
  placement?: Placement | null
  building: string
  floor: string
  enabled: boolean
  feed: 'live' | 'waiting' | 'offline' | 'paused'
  analysis: 'current' | 'waiting' | 'unavailable' | 'paused'
  generation: string | null
  framesReceived: number
  framesAnalyzed: number
  framesReplaced: number
  compute?: 'device' | 'pc' | null
  deviceStatus?: { state: 'loading' | 'ready' | 'error'; delegate: 'GPU' | 'CPU' | null; detail: string } | null
  error?: string | null
  result?: {
    backend?: 'camera-device' | 'local-ai'
    delegate?: 'GPU' | 'CPU'
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
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}
export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<T> {
  const token = await sessionToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api/v2${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    body: body ? (isForm ? (body as FormData) : JSON.stringify(body)) : undefined,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new ApiError(
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed (${response.status}).`,
      response.status,
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
export function socketUrl(path: string) {
  return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v2${path}`
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
      maxPeople: 10,
    }),
  )
  const packet = new Uint8Array(4 + header.length + jpeg.size)
  new DataView(packet.buffer).setUint32(0, header.length, true)
  packet.set(header, 4)
  packet.set(new Uint8Array(await jpeg.arrayBuffer()), 4 + header.length)
  return packet.buffer
}
