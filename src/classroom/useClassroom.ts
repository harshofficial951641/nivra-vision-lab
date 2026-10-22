import { useEffect, useRef, useState } from 'react'
import { api, openSocket, type Snapshot } from './contracts'
import { authenticateSocket } from '../auth/session'
import { NativeVideoBus, nativeVideoPacket } from './nativeVideo'
import { PreviewHistory, type CameraPreview } from './previewHistory'
export function useClassroom(
  enabled: boolean,
  onFrame?: (cameraId: string, jpeg: Blob, receivedAt: number) => void,
  /** Command system: authenticate the socket with the signed-in session instead of the operator cookie. */
  tokenAuth = false,
) {
  const frameListener = useRef(onFrame)
  useEffect(() => {
    frameListener.current = onFrame
  })
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [connection, setConnection] = useState<
    'connecting' | 'connected' | 'disconnected'
  >('connecting')
  const [error, setError] = useState('')
  const [apiAvailable, setApiAvailable] = useState(false)
  const [previews, setPreviews] = useState<Record<string, CameraPreview>>({})
  const [analysisPreviews, setAnalysisPreviews] = useState<Record<string, CameraPreview>>({})
  const [nativeVideo] = useState(() => new NativeVideoBus())
  const latest = useRef<Snapshot | null>(null)
  useEffect(() => {
    nativeVideo.clear()
    if (!enabled) { latest.current = null; setSnapshot(null); setPreviews({}); setAnalysisPreviews({}); setApiAvailable(false); setConnection('disconnected'); return }
    latest.current = null
    setSnapshot(null); setApiAvailable(false); setPreviews({}); setAnalysisPreviews({})
    let stopped = false,
      socket: WebSocket | null = null,
      timer = 0,
      attempts = 0
    let epoch = 0, deadline = 0, pollTimer = 0, revision = 0
    let healthy = false, polling = false
    const requests = new AbortController()
    const urls = new Map<string, string>()
    const previewGenerations = new Map<string, string>()
    const history = new PreviewHistory()
    const refreshAnalysisPreviews = () => {
      const matched: Record<string, CameraPreview> = {}
      for (const camera of latest.current?.cameras ?? []) {
        if (camera.feed !== 'live' || !camera.generation || !camera.result) continue
        const frame = history.select(camera.id, camera.generation, camera.result.timestampMs, Date.now())
        if (frame) matched[camera.id] = frame
      }
      setAnalysisPreviews(matched)
    }
    type Preview = { cameraId: string; generation: string; timestampMs: number; width: number; height: number }
    const pending = new Map<string, { meta: Preview; bytes: ArrayBuffer; offset: number; received: number }>()
    let paintTimer = 0
    const flushFrames = () => {
      paintTimer = 0
      if (stopped) return
      const batch: typeof previews = {}
      for (const [id, frame] of pending) {
        if (!latest.current?.cameras.some(camera => camera.id === id && camera.feed === 'live' && camera.generation === frame.meta.generation)) continue
        const jpeg = new Blob([frame.bytes.slice(frame.offset)], { type: 'image/jpeg' })
        frameListener.current?.(id, jpeg, frame.received)
        history.add(id, frame.meta, jpeg, frame.received)
        const url = URL.createObjectURL(jpeg)
        const previous = urls.get(id)
        urls.set(id, url)
        previewGenerations.set(id, frame.meta.generation)
        batch[id] = { ...frame.meta, url, received: frame.received }
        if (previous) URL.revokeObjectURL(previous)
      }
      pending.clear()
      refreshAnalysisPreviews()
      if (Object.keys(batch).length) setPreviews(old => ({ ...old, ...batch }))
    }
    const clearFrames = () => {
      nativeVideo.clear()
      clearTimeout(paintTimer)
      paintTimer = 0
      pending.clear()
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
      previewGenerations.clear()
      history.clear()
      setAnalysisPreviews({})
      setPreviews({})
    }
    const validSnapshot = (data: Snapshot) => !!data && (data.version === 2 || data.version === 3) && data.type === 'snapshot' && Array.isArray(data.cameras) && Array.isArray(data.events)
    const applySnapshot = (data: Snapshot) => {
      revision++
      setApiAvailable(true)
      latest.current = data
      setSnapshot(data)
      const active = new Map(
        data.cameras
          .filter((camera) => camera.feed === 'live')
          .map((camera) => [camera.id, camera.generation] as const),
      )
      nativeVideo.retain(active)
      urls.forEach((url, id) => {
        if (active.get(id) !== previewGenerations.get(id)) {
          URL.revokeObjectURL(url)
          urls.delete(id)
          previewGenerations.delete(id)
          if (pending.get(id)?.meta.generation !== active.get(id)) pending.delete(id)
        }
      })
      setPreviews((old) =>
        Object.fromEntries(
          Object.entries(old).filter(([id, frame]) => active.get(id) === frame.generation),
        ),
      )
      history.retain(active)
      refreshAnalysisPreviews()
    }
    const poll = async () => {
      if (stopped || polling || healthy) return
      clearTimeout(pollTimer)
      polling = true
      const before = revision
      try {
        const data = await api<Snapshot>('/state', 'GET', undefined, { signal: requests.signal, timeoutMs: 8000 })
        if (stopped) return
        if (!validSnapshot(data)) throw new Error('Invalid service response.')
        if (before !== revision || healthy) return
        applySnapshot(data)
      } catch (reason) {
        if (!stopped && before === revision && !healthy) {
          setApiAvailable(false)
          if (reason && typeof reason === 'object' && 'status' in reason && [401, 403].includes(Number(reason.status))) {
            revision++; latest.current = null; setSnapshot(null); clearFrames()
          }
        }
      } finally {
        polling = false
        if (!stopped) pollTimer = window.setTimeout(() => void poll(), 5000)
      }
    }
    const connect = async () => {
      const current = ++epoch
      healthy = false
      clearTimeout(deadline)
      deadline = window.setTimeout(() => { if (!stopped && current === epoch) { setError('Live connection timed out. Retrying…'); retry() } }, 12000)
      setConnection('connecting')
      try {
        if (!tokenAuth) await api('/session', 'POST')
        if (stopped || current !== epoch) return
        const peer = await openSocket('/operator')
        if (stopped || current !== epoch) { peer.close(); return }
        socket = peer
        if (tokenAuth) authenticateSocket(socket)
        socket.binaryType = 'arraybuffer'
        socket.onopen = () => { /* Wait for an authenticated snapshot. */ }
        socket.onmessage = (event) => {
          if (stopped || current !== epoch || socket !== peer) return
          try {
            if (typeof event.data === 'string') {
              const data = JSON.parse(event.data) as Snapshot
              if (
                (data.version !== 2 && data.version !== 3) ||
                data.type !== 'snapshot' ||
                !Array.isArray(data.cameras) ||
                !Array.isArray(data.events)
              )
                throw new Error('Unsupported service response')
              clearTimeout(deadline)
              healthy = true
              attempts = 0
              setConnection('connected')
              setError('')
              applySnapshot(data)
            } else {
              const bytes = event.data as ArrayBuffer
              if (bytes.byteLength < 5) return
              const size = new DataView(bytes).getUint32(0, true)
              if (size > 24576 || size + 4 >= bytes.byteLength) return
              const meta = JSON.parse(new TextDecoder().decode(bytes.slice(4, 4 + size)))
              if (meta.encoding === 'h264') {
                const packet = nativeVideoPacket(bytes)
                if (packet) nativeVideo.publish(packet)
                return
              }
              if (size > 1024) return
              if (!latest.current?.cameras.some((c) => c.id === meta.cameraId))
                return
              // Coalesce cameras into one paint and decode only the newest
              // frame per camera when network packets arrive in a burst.
              pending.set(meta.cameraId, { meta, bytes, offset: 4 + size, received: Date.now() })
              if (!paintTimer) paintTimer = window.setTimeout(flushFrames, 80)
            }
          } catch {
            setError('Invalid service response. Reconnect the service.')
            retry()
          }
        }
        socket.onclose = (event) => {
          if (stopped || current !== epoch || socket !== peer) return
          if (event.code === 1013 && event.reason) setError(event.reason)
          if (event.code === 4401 || event.code === 4403) { revision++; latest.current = null; setSnapshot(null); setApiAvailable(false) }
          if (event.code === 4401) setError('Your session expired. Sign in again.')
          if (event.code === 4403) setError('This account cannot open Command.')
          if (!stopped) retry()
        }
        socket.onerror = () => {
          if (stopped || current !== epoch || socket !== peer) return
          setError('Service connection interrupted.')
          retry()
        }
      } catch (reason) {
        if (!stopped && current === epoch) {
          setError(
            reason instanceof Error
              ? reason.message
              : 'Local service unavailable.',
          )
          retry()
        }
      }
    }
    const retry = () => {
      epoch++
      healthy = false
      clearTimeout(deadline)
      const previous = socket
      socket = null
      if (previous) { previous.onclose = null; previous.onmessage = null; previous.onopen = null; previous.onerror = null; previous.close() }
      setConnection('disconnected')
      clearFrames()
      void poll()
      window.clearTimeout(timer)
      timer = window.setTimeout(
        () => void connect(),
        Math.min(15000, 1000 * 2 ** Math.min(attempts++, 4)),
      )
    }
    const resume = () => {
      if (stopped || document.visibilityState === 'hidden') return
      clearTimeout(timer)
      clearTimeout(deadline)
      epoch++
      const previous = socket; socket = null
      if (previous) { previous.onclose = null; previous.close() }
      clearFrames()
      healthy = false
      void poll()
      void connect()
    }
    window.addEventListener('online', resume)
    document.addEventListener('visibilitychange', resume)
    void poll()
    void connect()
    return () => {
      stopped = true
      nativeVideo.clear()
      epoch++
      requests.abort()
      window.removeEventListener('online', resume)
      document.removeEventListener('visibilitychange', resume)
      clearTimeout(deadline)
      clearTimeout(pollTimer)
      clearTimeout(timer)
      clearTimeout(paintTimer)
      pending.clear()
      socket?.close()
      urls.forEach((url) => URL.revokeObjectURL(url))
      history.clear()
    }
  }, [enabled, tokenAuth, nativeVideo])
  return { snapshot, connection, error, previews, analysisPreviews, apiAvailable, nativeVideo }
}
