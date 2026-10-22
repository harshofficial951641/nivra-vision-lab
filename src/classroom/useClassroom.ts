import { useEffect, useRef, useState } from 'react'
import { api, socketUrl, type Snapshot } from './contracts'
import { authenticateSocket } from '../auth/session'
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
  const [previews, setPreviews] = useState<
    Record<
      string,
      {
        url: string
        generation: string
        received: number
        timestampMs: number
        width: number
        height: number
      }
    >
  >({})
  const latest = useRef<Snapshot | null>(null)
  useEffect(() => {
    if (!enabled) return
    let stopped = false,
      socket: WebSocket | null = null,
      timer = 0,
      attempts = 0
    const urls = new Map<string, string>()
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
        const url = URL.createObjectURL(jpeg)
        const previous = urls.get(id)
        urls.set(id, url)
        batch[id] = { ...frame.meta, url, received: frame.received }
        if (previous) URL.revokeObjectURL(previous)
      }
      pending.clear()
      if (Object.keys(batch).length) setPreviews(old => ({ ...old, ...batch }))
    }
    const clearFrames = () => {
      clearTimeout(paintTimer)
      paintTimer = 0
      pending.clear()
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
      setPreviews({})
    }
    const connect = async () => {
      setConnection('connecting')
      try {
        if (!tokenAuth) await api('/session', 'POST')
        if (stopped) return
        socket = new WebSocket(socketUrl('/operator'))
        if (tokenAuth) authenticateSocket(socket)
        socket.binaryType = 'arraybuffer'
        socket.onopen = () => {
          attempts = 0
          setConnection('connected')
          setError('')
        }
        socket.onmessage = (event) => {
          if (stopped) return
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
              latest.current = data
              setSnapshot(data)
              const active = new Set(
                data.cameras
                  .filter((camera) => camera.feed === 'live')
                  .map((camera) => camera.id),
              )
              urls.forEach((url, id) => {
                if (!active.has(id)) {
                  URL.revokeObjectURL(url)
                  urls.delete(id)
                  pending.delete(id)
                }
              })
              setPreviews((old) =>
                Object.fromEntries(
                  Object.entries(old).filter(([id]) => active.has(id)),
                ),
              )
            } else {
              const bytes = event.data as ArrayBuffer,
                size = new DataView(bytes).getUint32(0, true)
              if (size > 1024 || size + 4 >= bytes.byteLength) return
              const meta = JSON.parse(
                new TextDecoder().decode(bytes.slice(4, 4 + size)),
              ) as {
                cameraId: string
                generation: string
                timestampMs: number
                width: number
                height: number
              }
              if (!latest.current?.cameras.some((c) => c.id === meta.cameraId))
                return
              // Coalesce cameras into one paint and decode only the newest
              // frame per camera when network packets arrive in a burst.
              pending.set(meta.cameraId, { meta, bytes, offset: 4 + size, received: Date.now() })
              if (!paintTimer) paintTimer = window.setTimeout(flushFrames, 80)
            }
          } catch {
            setError('Invalid service response. Reconnect the service.')
            socket?.close()
          }
        }
        socket.onclose = (event) => {
          if (event.code === 1013 && event.reason) setError(event.reason)
          if (event.code === 4401) setError('Your session expired. Sign in again.')
          if (event.code === 4403) setError('This account cannot open Command.')
          if (!stopped) retry()
        }
        socket.onerror = () => {
          setError('Service connection interrupted.')
        }
      } catch (reason) {
        if (!stopped) {
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
      setConnection('disconnected')
      clearFrames()
      window.clearTimeout(timer)
      timer = window.setTimeout(
        () => void connect(),
        Math.min(15000, 1000 * 2 ** Math.min(attempts++, 4)),
      )
    }
    void connect()
    return () => {
      stopped = true
      clearTimeout(timer)
      clearTimeout(paintTimer)
      pending.clear()
      socket?.close()
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [enabled, tokenAuth])
  return { snapshot, connection, error, previews }
}
