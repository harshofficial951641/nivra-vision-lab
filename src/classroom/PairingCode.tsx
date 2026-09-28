import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'

export function PairingCode({ url, expiresAt, remoteReady, renew }: {
  url: string; expiresAt: number; remoteReady: boolean; renew: () => void
}) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.ceil((expiresAt - now) / 1000))
  return <div className="nv-pairing-code">
    {remoteReady && seconds > 0 ? <>
      <QRCodeSVG value={url} size={224} level="M" marginSize={4} title="Scan with your phone camera to connect this classroom" />
      <strong>Scan with your phone’s Camera app</strong>
      <p>Tap the link, allow camera access, then tap Start camera. Keep that page open.</p>
      <span>Expires in {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')} · one device only</span>
    </> : <p>{seconds === 0 ? 'This pairing code has expired.' : 'Phone QR pairing becomes available when the public bridge is connected.'}</p>}
    {seconds === 0 && <button className="nv-primary" onClick={renew}>Generate a new code</button>}
  </div>
}
