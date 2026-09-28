import { useEffect, useState, type ReactNode } from 'react'
import { api, isLocalDashboard } from './contracts'
import './classroom.css'

let exchange: Promise<unknown> | null = null
function enter() {
  if (!exchange) {
    const token = new URLSearchParams(location.hash.slice(1)).get('operator')
    if (token) history.replaceState(null, '', location.pathname)
    exchange = token ? api('/operator/redeem', 'POST', { token }) : api('/session', 'POST')
  }
  return exchange
}
export default function AccessGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(isLocalDashboard)
  const [error, setError] = useState('')
  useEffect(() => {
    if (isLocalDashboard) return
    let active = true
    void enter().then(() => { if (active) setReady(true) }).catch((reason) => {
      if (active) setError(reason.message)
    })
    return () => { active = false }
  }, [])
  if (ready) return children
  return <main className="nv-access-page">
    <section className="nv-content-panel nv-access-panel">
      <img src="/brand/nivra-mark.png" width="44" height="44" alt="Nivra" />
      <p className="nv-muted">CLASSROOM COMMAND</p>
      <h1>{error ? 'Unlock your dashboard' : 'Connecting to Nivra…'}</h1>
      <p>Camera feeds and incident records are private. On the analysis PC, open Nivra → Settings → Open public dashboard.</p>
      <p>That link works once within five minutes and signs this browser in for eight hours. Phones use a separate camera QR code.</p>
      {error && <p role="alert" className="nv-notice nv-warning">{error}</p>}
      <button className="nv-secondary" onClick={() => location.reload()}>Check connection again</button>
    </section>
  </main>
}
