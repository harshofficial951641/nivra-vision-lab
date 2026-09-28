export const isLocalDashboard = ['localhost', '127.0.0.1'].includes(location.hostname)
export interface CameraLocation {
  id: string
  name: string
  building: string
  floor: string
  enabled: boolean
  feed: 'live' | 'waiting' | 'offline' | 'paused'
  analysis: 'current' | 'waiting' | 'unavailable' | 'paused'
  generation: string | null
  framesReceived: number
  framesAnalyzed: number
  framesReplaced: number
  error?: string | null
  result?: {
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
}
export interface Snapshot {
  version: 2
  type: 'snapshot'
  cameras: CameraLocation[]
  events: Incident[]
  analytics: { total: number; pending: number; resolved: number }
  service: 'ready' | 'loading' | 'error'
  publicOrigin: string | null
  retention: 'event-records-only'
  experimental: true
  runtime: {
    personModel?: string
    fightModel?: string
    maxPeople?: number
  } | null
}
export async function api<T>(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/v2${path}`, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(
      typeof payload?.detail === 'string'
        ? payload.detail
        : `Request failed (${response.status}).`,
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
): Promise<ArrayBuffer | null> {
  if (!video.videoWidth || video.readyState < 2) return null
  const scale = Math.min(1, 960 / Math.max(video.videoWidth, video.videoHeight))
  canvas.width = Math.round(video.videoWidth * scale)
  canvas.height = Math.round(video.videoHeight * scale)
  const context = canvas.getContext('2d')
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
      maxPeople: 4,
    }),
  )
  const packet = new Uint8Array(4 + header.length + jpeg.size)
  new DataView(packet.buffer).setUint32(0, header.length, true)
  packet.set(header, 4)
  packet.set(new Uint8Array(await jpeg.arrayBuffer()), 4 + header.length)
  return packet.buffer
}
