import { useCallback, useEffect, useRef, useState } from 'react'
import './FightDemo.css'

type Result = { type: 'result'; streamId: number; timestampMs: number; status: 'warming' | 'review' | 'clear'; classifierScore: number | null; inferenceMs: number; analyzed: boolean }
type Health = { status: string; device?: string }

function waitFor(video: HTMLVideoElement, event: 'loadeddata' | 'seeked', action: () => void) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => finish(new Error('Video could not be read. Try another MP4 or WebM.')), 15000)
    const done = () => finish()
    const failed = () => finish(new Error('This browser cannot decode the video. Try an H.264 MP4 or WebM.'))
    function finish(error?: Error) {
      clearTimeout(timer)
      video.removeEventListener(event, done)
      video.removeEventListener('error', failed)
      if (error) reject(error); else resolve()
    }
    video.addEventListener(event, done, { once: true })
    video.addEventListener('error', failed, { once: true })
    action()
  })
}

export default function FightDemo() {
  const video = useRef<HTMLVideoElement>(null)
  const socket = useRef<WebSocket | null>(null)
  const camera = useRef<MediaStream | null>(null)
  const fileUrl = useRef<string | null>(null)
  const selected = useRef<File | null>(null)
  const generation = useRef(0)
  const [health, setHealth] = useState<Health>({ status: 'connecting' })
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState('Choose a sample or your own video to try the model.')
  const [error, setError] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [fileName, setFileName] = useState('No video selected')
  const [sourceName, setSourceName] = useState('No source')
  const [windows, setWindows] = useState(0)
  const [positive, setPositive] = useState(0)

  const releaseResources = useCallback((dispose = false) => {
    generation.current++
    socket.current?.close()
    socket.current = null
    camera.current?.getTracks().forEach(track => track.stop())
    camera.current = null
    if (video.current) { video.current.pause(); video.current.srcObject = null }
    if (dispose && fileUrl.current) { URL.revokeObjectURL(fileUrl.current); fileUrl.current = null }
  }, [])

  function stop() {
    releaseResources()
    setRunning(false)
  }

  useEffect(() => {
    document.title = 'NIVRA · Fight Model Lab'
    let alive = true
    const check = async () => {
      try {
        const response = await fetch('/api/v2/fight/health', { signal: AbortSignal.timeout(8000) })
        if (!response.ok) throw new Error('Analysis PC offline')
        const value = await response.json() as Health
        if (alive) setHealth(value)
      } catch { if (alive) setHealth({ status: 'offline' }) }
    }
    void check()
    const timer = window.setInterval(() => void check(), 10000)
    return () => {
      alive = false
      clearInterval(timer)
      releaseResources(true)
    }
  }, [releaseResources])

  async function start(source: 'grappling' | 'boxing' | 'file' | 'camera') {
    stop()
    const current = generation.current
    const active = () => generation.current === current
    const element = video.current!
    setRunning(true); setError(''); setResult(null); setWindows(0); setPositive(0)
    setMessage('Connecting to the analysis PC…')
    try {
      const response = await fetch('/api/v2/fight/session', { method: 'POST', signal: AbortSignal.timeout(10000) })
      if (!response.ok) throw new Error(response.status === 503 ? 'The model is loading or the analysis PC is offline. Try again shortly.' : 'Could not start a model session. Refresh this page and retry.')
      if (!active()) return
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v2/fight/stream`)
      socket.current = ws
      let pending: { resolve: (value: Result) => void; reject: (error: Error) => void } | null = null
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(() => reject(new Error('The GPU connection timed out.')), 15000)
        ws.onmessage = event => {
          const value = JSON.parse(event.data) as { type: string }
          if (value.type === 'ready') { clearTimeout(timer); resolve() }
          if (value.type === 'result' && pending) { const waiting = pending; pending = null; waiting.resolve(value as Result) }
        }
        ws.onerror = () => { clearTimeout(timer); const reason = new Error('The GPU connection failed. Refresh and retry.'); pending?.reject(reason); pending = null; reject(reason) }
        ws.onclose = event => { clearTimeout(timer); const reason = new Error(event.code === 1013 ? 'The GPU is serving another demo. Try again after it stops.' : 'The analysis connection ended. Start again to reconnect.'); pending?.reject(reason); pending = null; reject(reason) }
      })
      if (!active()) return
      if (source === 'camera') {
        setSourceName('Live webcam')
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false })
        if (!active()) { stream.getTracks().forEach(track => track.stop()); return }
        camera.current = stream
        await waitFor(element, 'loadeddata', () => { element.removeAttribute('src'); element.srcObject = stream })
        await element.play()
      } else {
        let url: string
        if (source === 'file') {
          if (!selected.current) throw new Error('Choose a video first.')
          if (fileUrl.current) URL.revokeObjectURL(fileUrl.current)
          fileUrl.current = URL.createObjectURL(selected.current)
          url = fileUrl.current
          setSourceName(selected.current.name)
        } else {
          setSourceName(source === 'grappling' ? 'Grappling sample · recorded footage' : 'Shadowboxing sample · no contact')
          const sample = await fetch(`/fight-samples/${source}.webm`, { signal: AbortSignal.timeout(20000) })
          if (!sample.ok) throw new Error('The sample is unavailable. Choose your own video or retry.')
          const bytes = await sample.blob()
          if (!active()) return
          if (fileUrl.current) URL.revokeObjectURL(fileUrl.current)
          fileUrl.current = URL.createObjectURL(bytes)
          url = fileUrl.current
        }
        await waitFor(element, 'loadeddata', () => { element.srcObject = null; element.src = url; element.load() })
        if (!Number.isFinite(element.duration) || element.duration < 4) throw new Error('Use a video at least four seconds long.')
      }
      if (!active()) return
      ws.send(JSON.stringify({ type: 'reset', streamId: current }))
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')!
      const started = performance.now()
      let position = 0
      setMessage(source === 'camera' ? 'Collecting four seconds of live video…' : 'Scanning video on your PC GPU…')
      while (active()) {
        if (source !== 'camera') {
          if (position >= element.duration) break
          if (Math.abs(element.currentTime - position) > .001) await waitFor(element, 'seeked', () => { element.currentTime = position })
        }
        if (!active()) break
        const scale = Math.min(1, 640 / Math.max(element.videoWidth, element.videoHeight))
        canvas.width = Math.max(32, Math.round(element.videoWidth * scale))
        canvas.height = Math.max(32, Math.round(element.videoHeight * scale))
        context.drawImage(element, 0, 0, canvas.width, canvas.height)
        const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Could not read this frame.')), 'image/jpeg', .8))
        const timestamp = source === 'camera' ? performance.now() - started : Math.round(position * 1000)
        const header = new TextEncoder().encode(JSON.stringify({ version: 1, streamId: current, timestampMs: timestamp, maxPeople: 4 }))
        const jpeg = new Uint8Array(await blob.arrayBuffer())
        const packet = new Uint8Array(4 + header.length + jpeg.length)
        new DataView(packet.buffer).setUint32(0, header.length, true)
        packet.set(header, 4); packet.set(jpeg, 4 + header.length)
        const before = performance.now()
        const value = await new Promise<Result>((resolve, reject) => {
          const timer = window.setTimeout(() => { pending = null; reject(new Error('Inference timed out. Stop and retry.')) }, 15000)
          pending = { resolve: result => { clearTimeout(timer); resolve(result) }, reject: error => { clearTimeout(timer); reject(error) } }
          if (ws.readyState !== WebSocket.OPEN) { pending.reject(new Error('GPU connection closed.')); pending = null; return }
          ws.send(packet)
        })
        if (!active()) break
        setResult(previous => ({ ...value, inferenceMs: value.analyzed ? value.inferenceMs : previous?.inferenceMs ?? 0 }))
        if (value.analyzed) { setWindows(count => count + 1); if (value.status === 'review') setPositive(count => count + 1) }
        position += .1
        if (source === 'camera') await new Promise(resolve => window.setTimeout(resolve, Math.max(0, 100 - (performance.now() - before))))
      }
      if (active()) { stop(); setMessage('Analysis complete. Review signals describe overlapping windows, not separate incidents.') }
    } catch (reason) {
      if (active()) { stop(); setError(reason instanceof Error ? reason.message : 'Analysis failed. Please retry.'); setMessage('Analysis stopped.') }
    }
  }

  const ready = health.status === 'ready'
  return <main className="fight-page">
    <header className="fight-header"><div className="fight-brand"><img src="/brand/nivra-mark.png" width="32" height="32" alt="" /><strong>NIVRA</strong><span>MODEL LAB</span></div><span className={`fight-health ${ready ? 'ready' : ''}`} role="status">{ready ? `PC model ready · ${health.device ?? 'GPU'}` : health.status === 'loading' ? 'Model loading…' : 'Analysis PC offline'}</span></header>
    <section className="fight-heading"><p>PHYSICAL INTERACTION REVIEW</p><h1>Try the fight model.</h1><span>X3D-M runs on the analysis PC. Samples are recorded footage; your own video stays in memory and is not saved.</span></section>
    <div className="fight-grid">
      <section className="fight-view" aria-label="Video source"><div className="fight-source"><strong>{sourceName}</strong><span>{running ? 'Analyzing' : 'Ready to start'}</span></div><div className="fight-stage"><video ref={video} muted playsInline controls={!running && sourceName !== 'No source'} aria-label="Source video" /><div className="fight-stage-label">{result?.status === 'review' ? 'Review physical interaction' : result?.status === 'clear' ? 'No fight signal in latest window' : running ? 'Collecting video evidence…' : 'Choose a source below'}</div></div><div className="fight-controls"><button disabled={!ready || running} onClick={() => void start('grappling')}>Run grappling sample</button><button disabled={!ready || running} onClick={() => void start('boxing')}>Run non-fight sample</button><button disabled={!running} onClick={() => { stop(); setMessage('Stopped. Video history cleared.') }}>Stop</button></div></section>
      <aside className="fight-panel"><p className="fight-eyebrow">LATEST MODEL OUTPUT</p><h2 aria-live="polite">{result?.status === 'review' ? 'Needs human review' : result?.status === 'clear' ? 'No fight signal' : running ? 'Building a video window' : 'Waiting for a source'}</h2><dl><div><dt>Source time</dt><dd>{result ? `${(result.timestampMs / 1000).toFixed(1)} s` : '—'}</dd></div><div><dt>Window</dt><dd>4 seconds</dd></div><div><dt>Classifier score</dt><dd>{result?.classifierScore != null ? result.classifierScore.toFixed(3) : '—'}</dd></div><div><dt>Model processing</dt><dd>{result ? `${Math.round(result.inferenceMs)} ms` : '—'}</dd></div><div><dt>Windows analyzed</dt><dd>{windows}</dd></div><div><dt>Review windows</dt><dd>{positive}</dd></div></dl><p className="fight-note">The score is uncalibrated. It is not the probability of violence. This scene classifier does not identify people or confirm contact or intent.</p><label className="fight-file">Choose your video<input disabled={running} type="file" accept="video/*" onChange={event => { selected.current = event.target.files?.[0] ?? null; setFileName(selected.current?.name ?? 'No video selected') }} /></label><p className="fight-filename">{fileName}</p><button disabled={!ready || running || !selected.current} onClick={() => void start('file')}>Analyze selected video</button><button disabled={!ready || running} onClick={() => void start('camera')}>Start webcam</button><p className="fight-note">Frames travel encrypted to the owner’s PC through Sites. One demo runs at a time. Keep the browser in the foreground.</p></aside>
    </div>
    <p className="fight-progress" role="status">{message}</p>{error && <p className="fight-error" role="alert">{error}</p>}
    <footer className="fight-footer">Experimental model · Human review required · PC and public bridge must remain online <a href="/lab">Open original Vision Lab</a><details><summary>Sample credits</summary><p>Grappling: Kod B, “Lutte Africaine Francophonie 2017”, <a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>. <a href="https://commons.wikimedia.org/wiki/File:Lutte_Africaine_Francophonie_2017.webm">Source</a>. Shadowboxing: Evworo, “Boxing training”, <a href="https://creativecommons.org/licenses/by-sa/3.0/">CC BY-SA 3.0</a>. <a href="https://commons.wikimedia.org/wiki/File:Boxing_training.webm">Source</a>. Both samples are served unchanged. Model: visionlab-ai community X3D-M checkpoint, publisher declares MIT.</p></details></footer>
  </main>
}
