import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Check, DeviceMobile, WifiHigh, QrCode } from '@phosphor-icons/react'
import { QRCodeSVG } from 'qrcode.react'
import { Brand } from '../ui/Brand'
import { startQRScanner } from '../pairing/qrScanner'
import { localPhoneQR } from './localPhoneQR'
import './usb.css'

type UsbDevice = { id: string; name: string; connected: boolean; linked?: boolean; cameraId?: string | null; state: 'waiting' | 'live' | 'reconnecting' | 'error'; detail?: string }
type UsbStatus = { devices: UsbDevice[]; analysis: { status: string; detail?: string } }
const isLocalUsbHost = (host: string) => ['localhost', '127.0.0.1', '::1', '[::1]'].includes(host)

async function usbRequest<T>(path: string, signal: AbortSignal, method = 'GET', body?: unknown): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) abort()
  const timer = method === 'GET' || path === '/invite' ? setTimeout(abort, 8000) : undefined
  try {
    const response = await fetch(`/api/local${path}`, { method, credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}) })
    if (!response.ok) {
      const result = await response.json().catch(() => null)
      throw new Error(typeof result?.detail === 'string' ? result.detail : 'Could not reach the phone connection. Try again.')
    }
    return response.status === 204 ? undefined as T : response.json()
  } catch (error) {
    if (controller.signal.aborted && !signal.aborted) throw new Error('The phone connection took too long. Try again.')
    if (error instanceof TypeError) throw new Error('Could not reach NIVRA. Open it on your Mac and try again.')
    throw error
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort) }
}

export default function UsbSetup() {
  const local = isLocalUsbHost(location.hostname)
  const [enabled, setEnabled] = useState(false)
  const [invite, setInvite] = useState<{url:string; expires:number} | null>(null)
  const [now, setNow] = useState(Date.now)
  const [linkedNotice, setLinkedNotice] = useState<string | null>(null)
  const inviteBaseline = useRef(new Set<string>())
  const [status, setStatus] = useState<UsbStatus | null>(null)
  const [problem, setProblem] = useState('')
  const [pollProblem, setPollProblem] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [floor, setFloor] = useState('')
  const [busy, setBusy] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [scanOpen, setScanOpen] = useState(false)
  const [scanning, setScanning] = useState(false)
  const scanner = useRef<AbortController | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const saving = useRef(false)
  const lifetime = useRef<AbortController | null>(null)
  const refresh = useRef<() => Promise<void>>(async () => {})
  const generation = useRef(0)
  useEffect(() => {
    if (!local) return
    const controller = new AbortController()
    lifetime.current = controller
    const current = ++generation.current
    let timer: ReturnType<typeof setTimeout> | undefined
    let polling = false
    let waiters: (() => void)[] = []
    const poll = async () => {
      if (polling || controller.signal.aborted) return
      polling = true
      clearTimeout(timer)
      try {
        const result = await usbRequest<UsbStatus>('/devices', controller.signal)
        if (controller.signal.aborted || current !== generation.current) return
        if (!Array.isArray(result.devices) || !result.analysis) throw new Error('The phone connection is getting ready. Try again.')
        setStatus(result); setPollProblem('')
      } catch (error) {
        if (!controller.signal.aborted) setPollProblem(error instanceof Error ? error.message : 'Phone connection interrupted. Retrying…')
      } finally {
        polling = false
        const done = waiters; waiters = []; done.forEach(resolve => resolve())
        if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 1500)
      }
    }
    refresh.current = async () => {
      if (polling) await new Promise<void>(resolve => { waiters.push(resolve) })
      await poll()
    }
    void usbRequest<{ enabled: boolean }>('/config', controller.signal).then(config => {
      if (controller.signal.aborted) return
      if (!config.enabled) throw new Error('Open NIVRA on your Mac, then try again.')
      setEnabled(true); void poll()
    }).catch(error => {
      if (!controller.signal.aborted) setPollProblem(error instanceof Error ? error.message : 'Open NIVRA on your Mac, then try again.')
    })
    return () => { generation.current = current + 1; controller.abort(); scanner.current?.abort(); clearTimeout(timer); refresh.current = async () => {} }
  }, [local, attempt])
  useEffect(() => {
    if (!invite) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [invite])
  useEffect(() => {
    if (!invite) return
    const linked = status?.devices.find(device => device.linked && !inviteBaseline.current.has(device.id))
    if (linked) { setInvite(null); setLinkedNotice(linked.id) }
  }, [invite, status])
  const createInvite = async () => {
    if (saving.current || !lifetime.current || !enabled || !status) return
    saving.current = true
    const current = generation.current
    setBusy(true); setProblem(''); setLinkedNotice(null); setSelected(null); closeScanner()
    inviteBaseline.current = new Set(status?.devices.filter(device => device.linked).map(device => device.id) ?? [])
    try {
      const result = await usbRequest<{url:string;expiresInSeconds:number}>('/invite', lifetime.current.signal, 'POST')
      if (current !== generation.current || lifetime.current.signal.aborted) return
      const target = new URL(result.url)
      if (target.protocol !== 'nivra:' || target.hostname !== 'local-camera' || !/^#pair=[A-Za-z0-9_-]{43}$/.test(target.hash) || !Number.isFinite(result.expiresInSeconds) || result.expiresInSeconds <= 0 || result.expiresInSeconds > 300) throw new Error('Could not create a camera QR. Try again.')
      const time = Date.now(); setNow(time)
      setInvite({url:result.url,expires:time + result.expiresInSeconds * 1000})
    } catch (error) {
      if (current === generation.current && !lifetime.current.signal.aborted) setProblem(error instanceof Error ? error.message : 'Could not create a camera QR. Try again.')
    } finally { saving.current = false; if (current === generation.current) setBusy(false) }
  }
  const closeScanner = () => {
    scanner.current?.abort(); scanner.current = null
    setScanning(false); setScanOpen(false)
  }
  const saveConnection = async (target: { deviceId: string; code: string } | { host: string; hosts?: string[]; code: string }) => {
    if (saving.current || !lifetime.current) return
    saving.current = true
    const current = generation.current
    closeScanner(); setBusy(true); setProblem('')
    try {
      await usbRequest('/connect', lifetime.current.signal, 'POST', { ...target, ...('host' in target ? { name: '', floor: '' } : { name: name.trim(), floor: floor.trim() }) })
      if (current !== generation.current) return
      setSelected(null); setCode(''); setName(''); setFloor('')
      await refresh.current()
    } catch (error) {
      if (current === generation.current) setProblem(error instanceof Error ? error.message : 'Could not connect this phone. Check its code and try again.')
    } finally { saving.current = false; if (current === generation.current) setBusy(false) }
  }
  const scanPhone = async () => {
    if (saving.current || scanner.current || !video.current) return
    const current = generation.current
    const controller = new AbortController()
    scanner.current = controller
    setScanOpen(true); setScanning(true); setSelected(null); setProblem('')
    try {
      await startQRScanner(video.current, text => {
        if (current !== generation.current || controller.signal.aborted || saving.current) return
        const target = localPhoneQR(text)
        if (!target) { setProblem('Use the QR shown in NIVRA on your camera phone.'); return }
        void saveConnection(target)
      }, controller.signal)
    } catch {
      if (current !== generation.current || controller.signal.aborted) return
      scanner.current = null; setScanning(false)
      setProblem('Camera unavailable. Allow camera access, or choose your phone and enter its code.')
    }
  }
  const connect = async (event: FormEvent) => {
    event.preventDefault()
    const normalized = code.toUpperCase().replace(/[\s-]/g, '')
    if (selected && /^[A-Z0-9]{8}$/.test(normalized)) await saveConnection({ deviceId: selected, code: normalized })
  }
  const remove = async (device: UsbDevice) => {
    if (saving.current || busy || !lifetime.current || !confirm(`Remove ${device.name} as a camera?`)) return
    const current = generation.current
    saving.current = true; setBusy(true); setProblem('')
    try {
      await usbRequest(`/devices/${encodeURIComponent(device.id)}`, lifetime.current.signal, 'DELETE')
      if (current === generation.current) await refresh.current()
    } catch (error) {
      if (current === generation.current) setProblem(error instanceof Error ? error.message : 'Could not remove this camera. Try again.')
    } finally { saving.current = false; if (current === generation.current) setBusy(false) }
  }
  if (!local) return <main className="usb-app usb-local-only"><Brand /><WifiHigh size={48} /><h1>Open NIVRA on your Mac.</h1><p>Join the same Wi-Fi router on your Mac and iPhones. Open Start NIVRA on the Mac.</p></main>
  const chosen = status?.devices.find(device => device.id === selected)
  const seconds = invite ? Math.max(0, Math.ceil((invite.expires-now)/1000)) : 0
  const linkedPhone = status?.devices.find(device => device.id === linkedNotice)
  const linkedPhones = status?.devices.filter(device => device.cameraId || device.linked) ?? []
  return <main className="usb-app">
    <header><Brand /><span>Phone cameras</span></header>
    <section className="usb-intro"><WifiHigh size={42} weight="light" /><h1>Add a camera.</h1><p>Join the same Wi-Fi router on this Mac and your iPhone. No internet or cable needed.</p></section>
    {enabled && !invite && !chosen && !scanOpen && <button type="button" className="usb-add-camera" disabled={busy || !status} onClick={() => void createInvite()}><QrCode aria-hidden size={24}/>{busy ? 'Getting QR ready…' : linkedPhones.length ? 'Add another camera' : 'Add camera'}</button>}
    {invite && <section className="usb-invite" aria-label="Connect your iPhone">
      <h2>Scan this QR with NIVRA.</h2>
      {seconds > 0 ? <><div className="usb-invite-qr"><QRCodeSVG value={invite.url} size={240} marginSize={3} title="Connect camera QR"/></div><ol className="usb-steps"><li>Open NIVRA on your iPhone.</li><li>Tap Scan to connect, then scan this QR.</li><li>Allow Camera and Local Network if asked.</li></ol><p role="status">Waiting for your phone · {Math.floor(seconds/60)}:{String(seconds%60).padStart(2,'0')}</p></> : <><p role="status">This QR has expired. Get a new one when your phone is ready.</p><button type="button" disabled={busy} onClick={() => void createInvite()}>New QR</button></>}
      <button type="button" className="usb-cancel" disabled={busy} onClick={() => setInvite(null)}>Close QR</button>
    </section>}
    {linkedPhone?.linked && <section className="usb-linked" role="status"><Check aria-hidden size={24}/><div><h2>{linkedPhone.state === 'live' ? 'Camera on' : 'Phone linked'}</h2><p>{linkedPhone.state === 'live' ? 'Your camera is ready to watch.' : 'Starting video. Keep NIVRA open on your phone.'}</p></div></section>}
    {(problem || pollProblem) && <div className="usb-problem"><p role="alert">{problem || pollProblem}</p><button type="button" disabled={busy} onClick={() => { setProblem(''); if (enabled) void refresh.current(); else setAttempt(value => value + 1) }}>Try again</button></div>}
    {!enabled && !problem && !pollProblem && <p role="status">Looking for your phones…</p>}
    {busy && <p role="status">Getting ready…</p>}
    <section className="usb-scanner" hidden={!scanOpen} aria-label="Scan your phone QR"><video ref={video} muted playsInline aria-label="QR camera preview" /><div className={scanning ? 'usb-scanner-guide is-scanning' : 'usb-scanner-guide'} aria-hidden /><p>Hold the phone’s QR in front of your Mac camera.</p>{!scanning && <button type="button" onClick={() => void scanPhone()}>Start scanner</button>}<button type="button" className="usb-cancel" onClick={() => { closeScanner(); setProblem('') }}>Cancel scanner</button></section>
    {enabled && !chosen && !scanOpen && <section className="usb-devices" aria-label="Your cameras">
      {linkedPhones.map(device => <article key={device.id} className="usb-device"><DeviceMobile size={32} weight="light"/><div><h2>{device.name}</h2><p role="status">{!device.connected ? 'Phone not found' : !device.linked ? 'Not connected' : device.state === 'live' ? 'Camera on' : device.state === 'reconnecting' ? 'Reconnecting…' : device.state === 'error' ? 'Needs attention' : 'Starting video…'}</p></div>{device.cameraId && <button type="button" disabled={busy} className="usb-remove" onClick={() => void remove(device)}>Remove</button>}{device.detail && <details><summary>Connection details</summary><p>{device.detail}</p></details>}</article>)}
    </section>}
    {enabled && !chosen && !scanOpen && !invite && <details className="usb-connect-help"><summary>Troubleshooting</summary><p>Keep NIVRA open on the iPhone and check that both devices joined the same Wi-Fi. If needed, enter its phone code below or scan the QR shown on the phone with this Mac.</p>{status?.devices.filter(device => device.connected && !device.linked).map(device => <div className="usb-fallback-phone" key={device.id}><span>{device.name}</span><button type="button" disabled={busy} onClick={() => { setSelected(device.id); setCode(''); setName(''); setFloor(''); setProblem('') }}>Use phone code</button></div>)}<button type="button" disabled={busy} onClick={() => void scanPhone()}><QrCode aria-hidden size={24}/>Scan phone QR</button></details>}
    {chosen && <section className="usb-connect" aria-label={`Connect ${chosen.name}`}><h2>One quick check.</h2><p>Enter the code shown in NIVRA on {chosen.name}.</p><form onSubmit={event => void connect(event)}>
      <label htmlFor="usb-code">Phone code</label><input id="usb-code" value={code} disabled={busy} onChange={event => { setCode(event.target.value.toUpperCase()); setProblem('') }} placeholder="ABCD 2345" autoComplete="off" autoCapitalize="characters" maxLength={12} required />
      <details><summary>Name and floor (optional)</summary><label htmlFor="usb-camera-name">Camera name</label><input id="usb-camera-name" value={name} maxLength={60} onChange={event => setName(event.target.value)} placeholder="e.g. Main entrance" /><label htmlFor="usb-camera-floor">Floor / area</label><input id="usb-camera-floor" value={floor} maxLength={60} onChange={event => setFloor(event.target.value)} placeholder="e.g. Ground floor" /></details>
      <button type="submit" disabled={busy || !chosen.connected || !/^[A-Z0-9]{8}$/.test(code.replace(/[\s-]/g, ''))}>{busy ? 'Connecting…' : 'Connect camera'}<ArrowRight aria-hidden /></button><button type="button" className="usb-cancel" disabled={busy} onClick={() => setSelected(null)}>Cancel</button>
    </form></section>}
    {status?.devices.some(device => device.cameraId && device.linked) && <a className="usb-watch" href="/wall">Watch cameras<ArrowRight aria-hidden /></a>}
    {status && <footer>{status.analysis.status === 'ready' ? <Check aria-hidden size={18} /> : <WifiHigh aria-hidden size={18} />}<span>{status.analysis.status === 'ready' ? 'Detection is ready on this Mac' : status.analysis.status === 'error' ? 'Detection needs attention' : 'Getting detection ready…'}</span>{status.analysis.detail && <details><summary>Details</summary><p>{status.analysis.detail}</p></details>}</footer>}
  </main>
}
