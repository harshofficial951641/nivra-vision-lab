import { useEffect, useRef, useState } from 'react'
import {
  Camera,
  Stop,
  ArrowClockwise,
  ShieldCheck,
} from '@phosphor-icons/react'
import { api, framePacket, socketUrl, type CameraLocation } from './contracts'
import { FrameWindow } from './frameWindow'
import './classroom.css'

// Module-scoped initial exchange is shared across React's StrictMode effect replay.
let pairingRequest: Promise<CameraLocation> | null = null
function initialPairing() {
  if (!pairingRequest) {
    const token = new URLSearchParams(location.hash.slice(1)).get('pair')
    history.replaceState(null, '', location.pathname)
    pairingRequest = token
      ? api('/camera/pair', 'POST', { token })
      : api('/camera/session')
  }
  return pairingRequest
}
export default function Publisher() {
  const [camera, setCamera] = useState<CameraLocation | null>(null),
    [error, setError] = useState('')
  const [lens, setLens] = useState('environment')
  const [status, setStatus] = useState<
      'idle' | 'starting' | 'live' | 'stopped'
    >('idle'),
    [sent, setSent] = useState(0)
  const video = useRef<HTMLVideoElement>(null),
    media = useRef<MediaStream | null>(null),
    socket = useRef<WebSocket | null>(null)
  const generation = useRef(0),
    timeout = useRef(0)
  const stop = () => {
    generation.current++
    clearTimeout(timeout.current)
    const peer = socket.current
    socket.current = null
    peer?.close()
    media.current?.getTracks().forEach((track) => track.stop())
    media.current = null
    if (video.current) video.current.srcObject = null
  }
  useEffect(() => {
    let active = true
    void initialPairing()
      .then((result) => {
        if (active) setCamera(result)
      })
      .catch((reason) => {
        if (active) setError(String(reason.message))
      })
    return () => {
      active = false
      stop()
    }
  }, [])
  const start = async () => {
    stop()
    const current = generation.current
    setError('')
    setStatus('starting')
    setSent(0)
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
        throw new Error(
          'A phone camera needs HTTPS. Open a secure pairing link from the dashboard.',
        )
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: lens },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      })
      if (current !== generation.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      media.current = stream
      if (!video.current) throw new Error('Camera preview unavailable')
      video.current.srcObject = stream
      await video.current.play()
      if (current !== generation.current) return
      const peer = new WebSocket(socketUrl('/camera/stream'))
      socket.current = peer
      const canvas = document.createElement('canvas')
      const flow = new FrameWindow()
      let sending = false
      const send = async () => {
        if (current !== generation.current) return
        const startedAt = performance.now()
        if (flow.timedOut(startedAt)) {
          peer.close()
          return
        }
        if (flow.canSend(startedAt, peer.bufferedAmount) && peer.readyState === WebSocket.OPEN && video.current) {
          let packet: ArrayBuffer | null
          try {
            packet = await framePacket(video.current, canvas, startedAt)
          } catch {
            peer.close()
            return
          }
          if (
            packet &&
            current === generation.current &&
            peer.readyState === WebSocket.OPEN &&
            flow.canSend(performance.now(), peer.bufferedAmount, packet.byteLength)
          ) {
            peer.send(packet)
            flow.sent(startedAt, performance.now(), packet.byteLength)
          }
        }
        if (current === generation.current)
          timeout.current = window.setTimeout(() => void send(), Math.max(0, 84 - (performance.now() - startedAt)))
      }
      peer.onmessage = (event) => {
        if (current !== generation.current) return
        const data = JSON.parse(event.data) as { type: string; timestampMs?: number }
        if (data.type === 'ready' && !sending) {
          sending = true
          setStatus('live')
          void send()
        }
        if (data.type === 'accepted' && typeof data.timestampMs === 'number' && flow.acknowledge(data.timestampMs)) {
          setSent((count) => count + 1)
        }
      }
      peer.onclose = () => {
        if (current === generation.current) {
          stop()
          setStatus('stopped')
          setError(
            'Connection ended. Keep this page open and reconnect when the service is available.',
          )
        }
      }
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        if (current === generation.current) {
          stop()
          setStatus('stopped')
          setError('Camera interrupted. Reconnect to resume.')
        }
      })
    } catch (reason) {
      if (current !== generation.current) return
      stop()
      setStatus('stopped')
      setError(
        reason instanceof Error ? reason.message : 'Camera could not start.',
      )
    }
  }
  return (
    <div className="nv-publisher nv-app">
      <header className="nv-publisher-brand">
        <img src="/brand/nivra-mark.png" alt="" />
        <strong>NIVRA</strong>
        <span>CAMERA</span>
      </header>
      <main>
        <p className="nv-eyebrow">CLASSROOM CONNECTION</p>
        <h1>{camera?.name || 'Connect a camera'}</h1>
        <p className="nv-muted">
          {camera
            ? `${camera.building} · ${camera.floor}`
            : 'Create a pairing link in the operator dashboard, then open it on this device.'}
        </p>
        <label className="nv-lens-select">
          Camera lens
          <select
            value={lens}
            disabled={status === 'live' || status === 'starting'}
            onChange={(event) => setLens(event.target.value)}
          >
            <option value="environment">Rear camera / default webcam</option>
            <option value="user">Front camera</option>
          </select>
        </label>
        <div className="nv-publisher-video">
          <video ref={video} muted playsInline autoPlay />
          <span className="nv-video-label">
            {status === 'live' ? 'Sending live frames' : 'Camera stopped'}
          </span>
        </div>
        {error && (
          <p role="alert" className="nv-notice nv-warning">
            {error}
          </p>
        )}
        <div className="nv-actions">
          {status === 'live' || status === 'starting' ? (
            <button
              className="nv-primary"
              onClick={() => {
                stop()
                setStatus('stopped')
                setError('')
              }}
            >
              <Stop />
              Stop camera
            </button>
          ) : (
            <button
              className="nv-primary"
              disabled={!camera}
              onClick={() => void start()}
            >
              {status === 'stopped' ? <ArrowClockwise /> : <Camera />}{' '}
              {status === 'stopped' ? 'Reconnect camera' : 'Start camera'}
            </button>
          )}
        </div>
        <p role="status">
          {sent > 0 ? `${sent} frames sent this session. ` : ''}Keep this page
          in the foreground and this device powered.
        </p>
        <section className="nv-privacy">
          <ShieldCheck size={24} />
          <div>
            <strong>Live video. No recordings.</strong>
            <p>
              Video frames travel to your operator’s computer for experimental
              analysis. Only event records are saved. Microphone is off.
            </p>
          </div>
        </section>
      </main>
    </div>
  )
}
