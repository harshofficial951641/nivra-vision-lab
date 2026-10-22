import { useEffect, useState } from 'react'
import { ArrowUpRight, Copy, LockKey } from '@phosphor-icons/react'
import { QRCodeSVG } from 'qrcode.react'
import { api } from '../classroom/contracts'
import { Brand } from '../ui/Brand'
import './mobile.css'

export default function OwnerAccess() {
  const local = ['127.0.0.1', 'localhost'].includes(location.hostname)
  const desktop = !/Android|iPhone|iPad|iPod/.test(navigator.userAgent) && !(navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  const [invite, setInvite] = useState<{ url: string; expires: number } | null>(null)
  const [now, setNow] = useState(Date.now)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!invite) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [invite])
  const create = async () => {
    if (!local || busy) return
    setBusy(true)
    setError('')
    setCopied(false)
    setInvite(null)
    try {
      await api('/session', 'POST')
      const result = await api<{ url: string; expiresInSeconds: number }>('/operator/invite', 'POST')
      const url = new URL(result.url)
      if (url.protocol !== 'https:' || url.username || url.password || !/^[A-Za-z0-9_-]{30,100}$/.test(new URLSearchParams(url.hash.slice(1)).get('operator') ?? '') ||
        !Number.isFinite(result.expiresInSeconds) || result.expiresInSeconds <= 0)
        throw new Error('The host returned an invalid owner link. Check the public connection, then try again.')
      const createdAt = Date.now()
      setInvite({ url: url.href, expires: createdAt + result.expiresInSeconds * 1000 })
      setNow(createdAt)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The host could not create an owner QR.')
    } finally { setBusy(false) }
  }
  const copy = async () => {
    if (!invite) return
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(invite.url)
      setCopied(true)
      setError('')
    } catch { setError('Copy was unavailable. Open the console link directly, or scan the QR.') }
  }
  const seconds = invite ? Math.max(0, Math.ceil((invite.expires - now) / 1000)) : 0
  return <main className="mh-app">
    <header className="mh-header"><a href="/" aria-label="NIVRA home"><Brand /></a><span className="mh-environment"><LockKey aria-hidden size={14} />Owner access</span></header>
    <section className="mh-owner" aria-labelledby="owner-title">
      <h1 id="owner-title">{local ? 'Open your place on another screen.' : 'Ask your owner for a QR.'}</h1>
      <p>{local ? 'Scan the QR on your other phone or computer to manage this place. It gives the first person owner access for eight hours.' : 'The owner can connect your screen with a private QR. Setting up a new place? Start from the NIVRA home page.'}</p>
      {!local && <><code className="mh-host-address">http://127.0.0.1:8765/owner</code>{desktop ? <><a className="mh-owner-open" href="http://127.0.0.1:8765/owner">Open owner access on this Mac <ArrowUpRight aria-hidden /></a><p>Use this only on the Mac running NIVRA. It opens the local owner page.</p></> : <p>Ask the site owner to create a private owner QR on the NIVRA computer, then scan it on this phone.</p>}</>}
      {local && <><p className="mh-owner-warning">Keep this QR private. Anyone who uses it first receives owner access. Creating another QR replaces the previous one.</p><button className="mh-owner-create" type="button" disabled={busy} onClick={() => void create()}>{busy ? 'Creating…' : invite ? 'Create a new owner QR' : 'Create owner QR'}<ArrowUpRight aria-hidden /></button></>}
      {error && <p className="mh-error" role="alert">{error}</p>}
      {invite && seconds > 0 && <div className="mh-owner-invite">
        <div className="mh-owner-qr"><QRCodeSVG value={invite.url} size={220} title="Private one-use NIVRA owner QR" /></div>
        <div className="mh-owner-invite-info"><span className="mh-eyebrow">One use · owner access</span><p role="status">Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}.</p><p>Scan with your phone’s camera and open the link. The owner link opens guided setup. Add cameras and guards, then open the wall.</p>
          <a className="mh-owner-open" href={invite.url} target="_blank" rel="noreferrer">Open public owner console <ArrowUpRight aria-hidden /></a>
          <button className="mh-owner-copy" type="button" onClick={() => void copy()}><Copy aria-hidden />{copied ? 'Private link copied' : 'Copy private owner link'}</button>
        </div>
      </div>}
      {invite && seconds === 0 && <p className="mh-owner-expired" role="status">This owner QR expired. Create another above.</p>}
      <a className="mh-owner-back" href="/mobile">Back to phones</a>
    </section>
  </main>
}
