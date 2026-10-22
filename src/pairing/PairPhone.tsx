import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, Check, QrCode, Keyboard } from '@phosphor-icons/react'
import { api } from '../classroom/contracts'
import { tokenForPhone } from './pairingToken'
import { startQRScanner } from './qrScanner'
import './pairing.css'

type Kind = 'camera' | 'guard'

export function PairPhone({ kind, onPaired }: { kind: Kind; onPaired: () => void }) {
  const [mode, setMode] = useState<'choose' | 'scan' | 'code'>('choose')
  const [code, setCode] = useState('')
  const [scanning, setScanning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')
  const video = useRef<HTMLVideoElement>(null)
  const codeInput = useRef<HTMLInputElement>(null)
  useEffect(() => { if (mode === 'code') codeInput.current?.focus() }, [mode])
  const scanner = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  const saving = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const callback = useRef(onPaired)
  callback.current = onPaired
  const stop = () => { scanner.current?.abort(); scanner.current = null }
  useEffect(() => () => { epoch.current++; stop(); if (timer.current) clearTimeout(timer.current) }, [])
  const back = () => {
    if (saving.current) return
    epoch.current++; stop(); setScanning(false); setMode('choose'); setError('')
  }
  const redeem = async (data: { token: string } | { code: string }) => {
    if (saving.current) return
    saving.current = true
    const current = epoch.current
    stop(); setScanning(false); setBusy(true); setError('')
    try {
      await api(`/${kind}/pair`, 'POST', data)
      if (current !== epoch.current) return
      setSuccess(true)
      const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
      timer.current = setTimeout(() => { if (current === epoch.current) callback.current() }, reduced ? 0 : 230)
    } catch (reason) {
      if (current === epoch.current) setError(reason instanceof Error ? reason.message : 'Could not connect. Ask your owner for a new code.')
    } finally {
      if (current === epoch.current) { saving.current = false; setBusy(false) }
    }
  }
  const scan = async () => {
    if (!video.current || scanner.current || saving.current) return
    setError(''); setScanning(true)
    const current = ++epoch.current
    const controller = new AbortController()
    scanner.current = controller
    try {
      await startQRScanner(video.current, text => {
        if (current !== epoch.current || controller.signal.aborted || saving.current) return
        const token = tokenForPhone(text, kind, location.origin)
        if (!token) { setError(`Use the ${kind} QR from this NIVRA site.`); return }
        void redeem({ token })
      }, controller.signal)
    } catch {
      if (current === epoch.current && !controller.signal.aborted) {
        stop(); setScanning(false); setError('Camera unavailable or permission blocked. Try again, or enter the code.')
      }
    }
  }
  const submit = (event: FormEvent) => {
    event.preventDefault()
    const normalized = code.toUpperCase().replace(/[\s-]/g, '')
    if (!/^[A-HJ-NP-Z2-9]{8}$/.test(normalized)) { setError('Enter the 8-character code shown on your owner screen.'); return }
    void redeem({ code: normalized })
  }
  if (success) return <section className="pp-phone pp-success" role="status"><span><Check size={38} weight="bold" /></span><h2>You're connected.</h2><p>Getting your {kind} ready…</p></section>
  return <section className="pp-phone" aria-label={`Connect ${kind} phone`}>
    <header><span className="pp-mark"><QrCode size={32} /></span><h2>Connect your {kind} phone</h2><p>Use the QR or code on your owner screen.</p></header>
    {mode === 'choose' ? <div className="pp-choices">
      <button type="button" onClick={() => { setMode('scan'); setError('') }}><QrCode size={28} /><span>Scan QR</span></button>
      <button type="button" onClick={() => { setMode('code'); setError('') }}><Keyboard size={28} /><span>Enter code</span></button>
    </div> : <div className="pp-entry" key={mode}>
      <button type="button" className="pp-back" disabled={busy} onClick={back}><ArrowLeft />Back</button>
      {mode === 'scan' ? <>
        <div className={`pp-viewfinder${scanning ? ' is-scanning' : ''}`}><video ref={video} muted playsInline aria-label="QR camera preview" /><div className="pp-scan-guide" aria-hidden /><p>{scanning ? 'Point at the QR on your owner screen.' : 'Camera off. Ready when you are.'}</p></div>
        {!scanning && !busy && <button type="button" className="pp-primary" onClick={() => void scan()}>Start scanner</button>}
        {scanning && <button type="button" className="pp-primary" onClick={back}>Cancel scanner</button>}
      </> : <form onSubmit={submit}><label htmlFor={`pp-code-${kind}`}>Pairing code</label><input ref={codeInput} id={`pp-code-${kind}`} value={code} onChange={event => { setCode(event.target.value.toUpperCase()); setError('') }} placeholder="ABCD 2345" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={12} disabled={busy} required /><button type="submit" className="pp-primary" disabled={busy || code.replace(/[\s-]/g, '').length !== 8}>Connect phone</button></form>}
    </div>}
    {busy && <p role="status">Connecting…</p>}
    {error && <p className="pp-error" role="alert">{error}</p>}
    <p className="pp-privacy">Scanning uses your camera only. No microphone.</p>
  </section>
}

export default PairPhone
