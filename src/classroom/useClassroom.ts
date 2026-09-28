import { useEffect, useRef, useState } from 'react'
import { api, socketUrl, type Snapshot } from './contracts'
export function useClassroom(enabled: boolean) {
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
    const clearFrames = () => {
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
      setPreviews({})
    }
    const connect = async () => {
      setConnection('connecting')
      try {
        await api('/session', 'POST')
        if (stopped) return
        socket = new WebSocket(socketUrl('/operator'))
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
                data.version !== 2 ||
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
              const url = URL.createObjectURL(
                  new Blob([bytes.slice(4 + size)], { type: 'image/jpeg' }),
                ),
                previous = urls.get(meta.cameraId)
              urls.set(meta.cameraId, url)
              setPreviews((old) => ({
                ...old,
                [meta.cameraId]: { ...meta, url, received: Date.now() },
              }))
              if (previous) URL.revokeObjectURL(previous)
            }
          } catch {
            setError('Invalid service response. Reconnect the service.')
            socket?.close()
          }
        }
        socket.onclose = (event) => {
          if (event.code === 1013 && event.reason) setError(event.reason)
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
      socket?.close()
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [enabled])
  return { snapshot, connection, error, previews }
}
