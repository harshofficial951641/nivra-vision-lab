import { useEffect, useRef, useState } from 'react'
import {
  Camera,
  Stop,
  ShieldCheck,
} from '@phosphor-icons/react'
import { ApiError, api, framePacket, openSocket, type CameraLocation } from './contracts'
import { coordinates, googleMapsURL } from '../location/gps'
import { useLiveGPS } from '../location/useLiveGPS'
import { FrameWindow } from './frameWindow'
import { DeviceReportQueue } from './deviceReportQueue'
import { TrackOverlay } from './TrackOverlay'
import { DeviceVision } from './DeviceVision'
import type { DeviceMotion, DeviceResult, DeviceStatus } from './deviceAnalysis'
import { analysisRegion, type AnalysisArea } from './deviceBudget'
import { detectionStatus } from './detectionStatus'
import { Brand } from '../ui/Brand'
import PairPhone from '../pairing/PairPhone'
import './classroom.css'

// Share the exchange across StrictMode replay, retaining failed links for retry.
let pairingRequest: { key: string; promise: Promise<CameraLocation> } | null = null
function initialPairing() {
  const token = new URLSearchParams(location.hash.slice(1)).get('pair')
  const key = token ? `pair:${token}` : 'session'
  if (pairingRequest?.key === key) return pairingRequest.promise
  const promise = (token ? api<CameraLocation>('/camera/pair', 'POST', { token }) : api<CameraLocation>('/camera/session'))
    .then(camera => {
      if (token && new URLSearchParams(location.hash.slice(1)).get('pair') === token)
        history.replaceState(null, '', location.pathname + location.search)
      if (pairingRequest?.promise === promise) pairingRequest = null
      return camera
    }).catch(reason => {
      if (pairingRequest?.promise === promise) pairingRequest = null
      throw reason
    })
  pairingRequest = { key, promise }
  return promise
}
export default function Publisher() {
  const [camera, setCamera] = useState<CameraLocation | null>(null),
    [error, setError] = useState('')
  const [locationEnabled, setLocationEnabled] = useState(false)
  const gps = useLiveGPS(!!camera && locationEnabled, async point => {
    const updated = await api<CameraLocation>('/camera/location', 'POST', point)
    setCamera(updated)
  })
  const options = useRef<HTMLDetailsElement>(null)
  const swipeStart = useRef<number | null>(null)
  const locationDetails = useRef<HTMLDetailsElement>(null)
  useEffect(() => { if (gps.error && locationDetails.current) locationDetails.current.open = true }, [gps.error])
  const [lens, setLens] = useState('environment')
  const [area, setArea] = useState<AnalysisArea>('full')
  const [aspect, setAspect] = useState(16 / 9)
  const [analysis, setAnalysis] = useState<DeviceStatus | null>(null)
  const [observation, setObservation] = useState<DeviceResult | null>(null)
  const [motion, setMotion] = useState<DeviceMotion | null>(null)
  const [motionStatus, setMotionStatus] = useState<DeviceStatus | null>(null)
  const detector = useRef<DeviceVision | null>(null)
  const [status, setStatus] = useState<
      'idle' | 'starting' | 'reconnecting' | 'live' | 'stopped'
    >('idle'),
    [sent, setSent] = useState(0)
  const video = useRef<HTMLVideoElement>(null),
    media = useRef<MediaStream | null>(null),
    socket = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef(0), connectionDeadline = useRef(0)
  const detectionRetry = useRef<() => void>(() => {})
  const resumeConnection = useRef<() => void>(() => {})
  const [pairingAttempt, setPairingAttempt] = useState(0)
  const [pairingBusy, setPairingBusy] = useState(true)
  const summary = detectionStatus({ phase: status, now: performance.now(), crowd: observation, crowdStatus: analysis, motion, motionStatus })
  const generation = useRef(0),
    timeout = useRef(0),
    analysisTimeout = useRef(0)
  const stop = () => {
    generation.current++
    clearTimeout(timeout.current)
    clearTimeout(reconnectTimeout.current)
    clearTimeout(connectionDeadline.current)
    detectionRetry.current = () => {}
    resumeConnection.current = () => {}
    clearTimeout(analysisTimeout.current)
    detector.current?.dispose()
    detector.current = null
    const peer = socket.current
    socket.current = null
    peer?.close()
    media.current?.getTracks().forEach((track) => track.stop())
    media.current = null
    if (video.current) video.current.srcObject = null
    setLocationEnabled(false)
  }
  useEffect(() => {
    const resume = () => { if (document.visibilityState !== 'hidden') resumeConnection.current() }
    window.addEventListener('online', resume)
    document.addEventListener('visibilitychange', resume)
    return () => { window.removeEventListener('online', resume); document.removeEventListener('visibilitychange', resume) }
  }, [])
  useEffect(() => {
    let active = true
    setPairingBusy(true)
    setError('')
    void initialPairing()
      .then((result) => {
        if (active) setCamera(result)
      })
      .catch((reason) => {
        if (active) setError(String(reason.message))
      }).finally(() => { if (active) setPairingBusy(false) })
    return () => {
      active = false
      stop()
    }
  }, [pairingAttempt])
  const start = async () => {
    stop()
    const current = generation.current
    setError('')
    setStatus('starting')
    setSent(0)
    setAnalysis(null)
    setObservation(null)
    setMotion(null)
    setMotionStatus(null)
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia)
        throw new Error(
          'Open this camera link in Safari or Chrome at nivra.tanishq.work to allow camera access.',
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
      setLocationEnabled(true)
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        if (current === generation.current) {
          stop(); setStatus('stopped')
          setError('Camera interrupted. Tap Allow camera & start to resume.')
        }
      })
      let reconnects = 0
      let connecting = false
      const retryConnection = (reason: unknown) => {
        if (current !== generation.current) return
        clearTimeout(timeout.current); clearTimeout(analysisTimeout.current); clearTimeout(connectionDeadline.current)
        detector.current?.dispose(); detector.current = null
        setObservation(null); setMotion(null); setSent(0)
        const peer = socket.current
        socket.current = null
        if (peer) { peer.onclose = null; peer.close() }
        if (reason instanceof ApiError && reason.status === 403) {
          stop(); setStatus('stopped')
          setCamera(null)
          setError('This phone needs pairing. Scan its camera QR from the owner screen.')
          return
        }
        setStatus('reconnecting'); setError('')
        const delay = [500, 1500, 3000, 5000][Math.min(reconnects++, 3)]
        if (navigator.onLine !== false) reconnectTimeout.current = window.setTimeout(() => { if (current === generation.current) void connect() }, delay)
      }
      const connect = async () => {
        if (connecting || current !== generation.current) return
        if (navigator.onLine === false) { setStatus('reconnecting'); return }
        connecting = true
        try {
          const peer = await openSocket('/camera/stream')
          if (current !== generation.current) { peer.close(); return }
          socket.current = peer
          const canvas = document.createElement('canvas')
          const flow = new FrameWindow()
          let sending = false
          const resultQueue = new DeviceReportQueue<DeviceResult>(200)
          const motionQueue = new DeviceReportQueue<DeviceMotion>(100)
          let shownAt = -Infinity
          let motionShownAt = -Infinity
          let acknowledged = 0, countShownAt = -Infinity
          const report = () => {
            if (current === generation.current && socket.current === peer && peer.readyState === WebSocket.OPEN && peer.bufferedAmount < 128 * 1024) {
              for (const queue of [motionQueue, resultQueue]) {
                const next = queue.take(performance.now())
                if (next) peer.send(JSON.stringify(next))
              }
            }
          }
          // Preview JPEG work can be slow on phones. It must not pace motion sampling.
          const analyze = () => {
            if (current !== generation.current || socket.current !== peer) return
            report()
            if (video.current) void detector.current?.capture(video.current, performance.now())
            analysisTimeout.current = window.setTimeout(analyze, 50)
          }
          const send = async () => {
            if (current !== generation.current || socket.current !== peer) return
            const startedAt = performance.now()
            report()
            if (flow.timedOut(startedAt)) {
              peer.close()
              return
            }
            if (flow.canSend(startedAt, peer.bufferedAmount) && peer.readyState === WebSocket.OPEN && video.current) {
              let packet: ArrayBuffer | null
              try {
                packet = await framePacket(video.current, canvas, startedAt, detector.current?.budget.previewSide)
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
            report()
            if (current === generation.current && socket.current === peer)
              timeout.current = window.setTimeout(() => void send(), Math.max(0, (detector.current?.budget.previewInterval ?? 84) - (performance.now() - startedAt)))
          }
          const startDetection = () => {
            if (current !== generation.current || peer.readyState !== WebSocket.OPEN) return
            detector.current?.dispose()
            resultQueue.clear(); motionQueue.clear()
            setObservation(null); setMotion(null); setSent(0)
            const client = new DeviceVision(
              (next) => {
                if (current !== generation.current || peer.readyState !== WebSocket.OPEN) return
                setAnalysis(next)
                resultQueue.clear()
                if (next.state !== 'ready') setObservation(null)
                peer.send(JSON.stringify({ type: 'device-status', ...next }))
              },
              (result) => {
                if (current !== generation.current || socket.current !== peer) return
                resultQueue.push(result)
                report()
                if (performance.now() - shownAt > 500 || result.conflict.status === 'alert') {
                  shownAt = performance.now()
                  setObservation(result)
                }
              },
              area, 'original',
              (result) => {
                if (current !== generation.current || socket.current !== peer) return
                motionQueue.push(result)
                report()
                if (performance.now() - motionShownAt >= 250 || result.conflict.status === 'alert') {
                  motionShownAt = performance.now()
                  setMotion(result)
                }
              },
              (next) => {
                if (current !== generation.current || peer.readyState !== WebSocket.OPEN) return
                setMotionStatus(next)
                if (next.state !== 'ready') { motionQueue.clear(); setMotion(null) }
                peer.send(JSON.stringify({ type: 'device-motion-status', ...next }))
              },
            )
            detector.current = client
            client.start()
          }
          detectionRetry.current = startDetection
          connectionDeadline.current = window.setTimeout(() => { if (current === generation.current && !sending) peer.close() }, 15000)
          peer.onmessage = (event) => {
            if (current !== generation.current || socket.current !== peer) return
            let data: { type: string; timestampMs?: number }
            try { data = JSON.parse(event.data) as typeof data }
            catch { retryConnection(new Error('Connection interrupted.')); return }
            if (data.type === 'ready' && !sending) {
              sending = true
              clearTimeout(connectionDeadline.current)
              setStatus('live')
              startDetection()
              analyze()
              void send()
            }
            if (data.type === 'accepted' && typeof data.timestampMs === 'number' && flow.acknowledge(data.timestampMs)) {
              acknowledged++
              if (performance.now() - countShownAt >= 500) {
                countShownAt = performance.now()
                setSent(acknowledged)
              }
            }
          }
          peer.onclose = () => { if (socket.current === peer) retryConnection(new Error('Connection lost.')) }
        } catch (reason) { retryConnection(reason) }
        finally { connecting = false }
          }
      resumeConnection.current = () => {
        if (current === generation.current && !socket.current && !connecting) {
          clearTimeout(reconnectTimeout.current)
          void connect()
        }
      }
      await connect()
    } catch (reason) {
      if (current !== generation.current) return
      stop()
      setStatus('stopped')
      setError(
        reason instanceof Error || reason instanceof DOMException
          ? reason.name === 'NotAllowedError' || reason.name === 'PermissionDeniedError'
            ? 'Camera access is blocked. Allow it in your browser settings, then try again.'
            : reason.name === 'NotFoundError'
              ? 'No camera was found. Open this link on your camera phone.'
              : reason.name === 'NotReadableError'
                ? 'Another app may be using the camera. Close it, then try again.'
                : reason.message
          : 'Camera could not start. Try again.',
      )
    }
  }
  const running = status === 'live' || status === 'starting' || status === 'reconnecting'
  if (new URLSearchParams(location.search).get('connect') === '1') return <PairPhone kind="camera" onPaired={() => location.replace('/camera')} />
  if (!camera && !pairingBusy && !new URLSearchParams(location.hash.slice(1)).has('pair')) return <PairPhone kind="camera" onPaired={() => setPairingAttempt(value => value + 1)} />
  return (
    <div className="nv-publisher nv-app nv-publisher--simple nv-camera-fullscreen">
      <header className="nv-publisher-brand">
        <Brand compact /><span className="nv-video-label">{status === 'live' ? sent > 0 ? 'Live' : 'Connecting to camera wall…' : status === 'reconnecting' ? 'Reconnecting…' : status === 'starting' ? 'Starting camera…' : 'Camera off'}</span>
      </header>
      <main>
        <h1>{camera?.name || 'Connect this phone'}</h1>
        <p className="nv-muted">{camera ? [camera.building, camera.floor].filter(Boolean).join(' · ') : pairingBusy ? 'Connecting your camera…' : 'Scan the camera QR from the owner screen.'}</p>
        <div className="nv-publisher-video" style={{ aspectRatio: aspect }}>
          <video ref={video} muted playsInline autoPlay onResize={event => { const node = event.currentTarget; if (node.videoHeight) setAspect(node.videoWidth / node.videoHeight) }} />
          {status === 'live' && observation && performance.now() - observation.timestampMs >= 0 && performance.now() - observation.timestampMs <= 1000 && <TrackOverlay tracks={observation.tracks.map(track => ({ ...track, observed: true, ambiguous: true }))} poses={observation.poses} width={video.current?.videoWidth || aspect * 1000} height={video.current?.videoHeight || 1000} />}
          {area !== 'full' && <div className="nv-analysis-region" style={{ left: `${analysisRegion(area).x * 100}%` }}><span>Analyzed area</span></div>}
          {!running && <p className="nv-camera-prompt">{camera ? 'Ready when you are.' : pairingBusy ? 'Connecting your camera…' : 'Pair this phone to start.'}</p>}
        </div>
        {error && <p role="alert" className="nv-notice nv-warning">{error}</p>}
        {!camera && !pairingBusy && <div className="nv-actions"><button type="button" className="nv-secondary" onClick={() => setPairingAttempt(value => value + 1)}>Try pairing again</button><a href="/camera?connect=1">Use a new QR or code</a></div>}
        {running && <section className="nv-detection-summary" data-state={summary.state} aria-label="Detection status">
          <div><strong role={summary.state === 'review' ? 'alert' : 'status'}>{summary.label}</strong><span>{summary.people} {summary.people === 1 ? 'person' : 'people'} detected</span></div>
          <p>{summary.action}</p>
          {summary.state === 'unavailable' && <button type="button" className="nv-secondary" onClick={() => detectionRetry.current()}>Retry detection</button>}
        </section>}
        <div className="nv-actions nv-camera-primary">
          {running ? <button className="nv-primary" onClick={() => { stop(); setStatus('stopped'); setError('') }}><Stop />Stop camera</button>
            : <button className="nv-primary" disabled={!camera || pairingBusy} onClick={() => void start()}><Camera />Allow camera &amp; start</button>}
        </div>
        <p className="nv-camera-hint">{running ? 'Keep this screen open.' : 'Tap once, then allow camera access. No app needed.'}</p>
        <details className="nv-phone-options" ref={options}>
          <summary onTouchStart={event => { swipeStart.current = event.touches[0]?.clientY ?? null }} onTouchEnd={event => {
            const end = event.changedTouches[0]?.clientY
            if (end !== undefined && swipeStart.current !== null && end - swipeStart.current > 60 && options.current) { event.preventDefault(); options.current.open = false }
            swipeStart.current = null
          }}>Options</summary>
          <div className="nv-phone-options-body">
          <button type="button" className="nv-secondary nv-close-options" onClick={() => { if (options.current) options.current.open = false }}>Close options</button>
          <p><a href="/camera?connect=1">Connect to another camera</a></p>
        <details className="nv-camera-details">
          <summary>Camera settings</summary>
          <label className="nv-lens-select">Camera lens<select value={lens} disabled={running} onChange={event => setLens(event.target.value)}><option value="environment">Rear camera / default webcam</option><option value="user">Front camera</option></select></label>
          <label className="nv-lens-select">Analyze area<select aria-label="Analyze area" value={area} disabled={running} onChange={event => setArea(event.target.value as AnalysisArea)}><option value="full">Whole frame</option><option value="left">Left half</option><option value="center">Center half</option><option value="right">Right half</option></select></label>
          <p className="nv-muted">Stop the camera to change these settings. People outside a focused area are not analyzed.</p>
        </details>
        <details className="nv-camera-details" ref={locationDetails}>
          <summary>Location {camera?.gps ? '· shared' : '· not shared yet'}</summary>
          <section aria-label="Camera GPS">
            <p role="status">{camera?.gps ? `${coordinates(camera.gps)} · accuracy ±${Math.ceil(camera.gps.accuracy)} m` : 'Waiting for a location. Video can work without GPS.'}</p>
            {gps.error && <p role="alert">{gps.error}</p>}
            <button type="button" className="nv-secondary" disabled={!camera} onClick={() => { setLocationEnabled(true); gps.retry() }}>{gps.error ? 'Retry GPS location' : 'Refresh GPS tracking'}</button>
            {camera?.gps && <p><a href={googleMapsURL(camera.gps)} target="_blank" rel="noreferrer">Open in Google Maps</a></p>}
            <p className="nv-muted">Floor: {camera?.floor || 'Not set'}. {gps.age !== null ? `Last shared ${gps.age}s ago. ` : ''}Indoor GPS may be imprecise.</p>
          </section>
        </details>
        <details className="nv-camera-details">
          <summary>Detection details</summary>
          <section aria-label="Device fight detection">
            <p>{analysis?.detail || 'Skeleton detection starts with the camera. Up to 4 skeletons per view.'}</p>
            <p>Shows up to 4 skeletons per view. Keep people and their arms visible.</p>
            {observation && <p>{observation.conflict.explanation} · {Math.round(observation.inferenceMs)} ms</p>}
            {motion && <p>{motion.conflict.explanation} · {Math.round(motion.inferenceMs)} ms</p>}
            <p>{sent} preview frames sent. Motion checks flag possible conflicts for a person to review. Hidden people and fast movements can be missed.</p>
          </section>
        </details>
          </div>
        </details>
        <p className="nv-camera-privacy"><ShieldCheck aria-hidden />Microphone off. Live previews go to your owner screen.</p>
      </main>
    </div>
  )
}
