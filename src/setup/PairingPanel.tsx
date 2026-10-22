import { useCallback, useEffect, useRef, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Check, Copy } from '@phosphor-icons/react'
import { api } from '../classroom/contracts'
import { useSession } from '../auth/context'
import './pairing-panel.css'
const messageOf = (reason: unknown) => reason instanceof Error ? reason.message : 'Could not create a pairing code.'
type PairingLink = { url: string; remoteReady: boolean; expires: number; duration: number; code?: string }

export function PairingPanel({ endpoint, label, kind, onClose, fail, connected = false, paired = false }: { endpoint: string; label: string; kind: 'camera' | 'guard'; onClose: () => void; fail: (reason: unknown) => void; connected?: boolean; paired?: boolean }) {
  const { mode } = useSession()
  const initialized = useRef(false)
  const [error, setError] = useState('')
  const [changingPhone, setChangingPhone] = useState(false)
  const [busy, setBusy] = useState(!connected && !paired)
  const [link, setLink] = useState<PairingLink | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [copied, setCopied] = useState<'code' | 'link' | null>(null)
  const failRef = useRef(fail)
  useEffect(() => { failRef.current = fail })
  const create = useCallback(async () => {
    setBusy(true); setError(''); setLink(null)
    try {
      const result = await api<{ url: string; remoteReady: boolean; expiresInSeconds: number; pairingCode?: string }>(endpoint, 'POST')
      const createdAt = Date.now()
      const code = result.pairingCode && /^[a-z0-9]{8}$/i.test(result.pairingCode) ? result.pairingCode.toUpperCase() : undefined
      setNow(createdAt)
      setLink({ url: result.url, remoteReady: result.remoteReady, expires: createdAt + result.expiresInSeconds * 1000, duration: result.expiresInSeconds, code })
      setCopied(null)
    } catch (reason) { setError(messageOf(reason)); failRef.current(reason) }
    finally { setBusy(false) }
  }, [endpoint])
  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true
      if (!connected && !paired) void create()
    }
  }, [create, connected, paired])
  useEffect(() => {
    if (connected || (paired && !changingPhone)) return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [connected, paired, changingPhone])
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(null), 2200)
    return () => clearTimeout(timer)
  }, [copied])
  const copy = async (value: string, target: 'code' | 'link') => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(value); setCopied(target); setError('')
    } catch { setError('Copy is unavailable. Scan the QR or type the code shown here.') }
  }
  useEffect(() => { if (!paired) setChangingPhone(false) }, [paired])
  const seconds = link ? Math.max(0, Math.ceil((link.expires - now) / 1000)) : 0
  return <div className="st-pair pp-panel">
    <header><strong>{connected ? label : `Connect ${label}`}</strong><button type="button" className="cm-link" onClick={onClose}>Close</button></header>
    {connected ? <div className="pp-connected" role="status"><span className="pp-success-mark" aria-hidden><Check weight="bold" /></span><h3>Phone connected</h3><p>{kind === 'camera' ? 'Your camera is live. You can watch it now.' : 'Your guard is online.'}</p><button type="button" className="cm-btn cm-btn--dark" onClick={onClose}>Done</button></div> : paired && !changingPhone ? <div className="pp-connected" role="status"><span className="pp-success-mark" aria-hidden><Check weight="bold" /></span><h3>Phone linked</h3><p>On that phone, tap Allow camera &amp; start.</p><p className="cm-muted">The camera will appear here once it starts.</p><button type="button" className="cm-btn" onClick={() => {
      if (!window.confirm('Change phone? The current phone will disconnect.')) return
      setChangingPhone(true)
      void create()
    }}>Change phone</button></div> : link && seconds > 0 ? <div className="st-pair-body">
      <div className="pp-qr"><QRCodeSVG value={link.url} size={220} marginSize={2} title={`Pairing code for ${label}`} /><span className="pp-corner pp-corner--tl" aria-hidden /><span className="pp-corner pp-corner--tr" aria-hidden /><span className="pp-corner pp-corner--bl" aria-hidden /><span className="pp-corner pp-corner--br" aria-hidden /></div>
      <div className="pp-instructions">
        <p>{kind === 'camera' ? 'On your phone, open Camera and scan this QR. It opens NIVRA in your browser. Tap Allow camera & start, then allow access.' : `Scan with the guard’s phone${mode === 'clerk' ? ', sign in with their account' : ''}, then tap Start shift and allow location.`}</p>
        {link.code && <details className="pp-code-block"><summary>Use a code instead</summary><div className="pp-code" aria-label={`Pairing code ${link.code}`}>{link.code.slice(0, 4)} {link.code.slice(4)}</div><button type="button" className="cm-btn pp-copy" data-copied={copied === 'code'} onClick={() => void copy(link.code!, 'code')}>{copied === 'code' ? <Check aria-hidden /> : <Copy aria-hidden />}<span aria-live="polite">{copied === 'code' ? 'Copied' : 'Copy code'}</span></button></details>}
        <div className="pp-expiry"><p className="cm-muted">Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} · one use only</p><div className="pp-time-track" aria-hidden><span style={{ transform: `scaleX(${link.duration > 0 ? Math.min(1, seconds / link.duration) : 0})` }} /></div></div>
        {!link.remoteReady && location.protocol !== 'https:' && <p className="cm-warn">Open the secure site address on this phone before pairing.</p>}
        <details className="pp-link"><summary>Use a link instead</summary><button type="button" className="cm-btn" onClick={() => void copy(link.url, 'link')}>{copied === 'link' ? <Check aria-hidden /> : <Copy aria-hidden />}{copied === 'link' ? 'Copied' : 'Copy link'}</button><code className="st-link">{link.url}</code></details>
        {error && <p role="alert" className="cm-error">{error}</p>}
      </div>
    </div> : <div className="st-pair-body pp-empty"><p className="cm-muted" role={error ? 'alert' : 'status'}>{error || (link ? 'This code has expired.' : busy ? 'Getting your code ready…' : 'Connect this phone again.')}</p>{!busy && <button type="button" className="cm-btn cm-btn--dark" onClick={() => void create()}>New code</button>}</div>}
  </div>
}
