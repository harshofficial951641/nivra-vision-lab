import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Camera, ShieldCheck } from '@phosphor-icons/react'
import { Brand } from '../ui/Brand'
import { ApiError, api } from '../classroom/contracts'
import type { Me } from '../auth/session'
import './mobile.css'

export default function WorkspaceStart() {
  const [name, setName] = useState('')
  const [checking, setChecking] = useState(true)
  const [fresh, setFresh] = useState(false)
  const [member, setMember] = useState<Me | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const check = useRef<{ attempt: number; promise: Promise<Me> } | null>(null)
  const creating = useRef(false)
  useEffect(() => {
    let active = true
    setChecking(true)
    setError('')
    if (!check.current || check.current.attempt !== attempt) check.current = { attempt, promise: api<Me>('/me') }
    void check.current.promise.then(me => {
      if (!active) return
      if (me.role === 'admin') {
        location.replace('/wall')
        return
      }
      setMember(me)
      setFresh(false)
    }).catch(reason => {
      if (!active) return
      if (reason instanceof ApiError && [401, 403].includes(reason.status)) setFresh(true)
      else { setFresh(false); setError('Could not check your saved workspace. Check the connection, then retry.') }
    }).finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [attempt])
  const create = async (event: FormEvent) => {
    event.preventDefault()
    if (!fresh || checking || creating.current) return
    creating.current = true
    setBusy(true)
    setError('')
    try {
      const result = await api<{ workspace: { id: string; name: string; ownerVerification: 'unverified' } }>('/workspaces', 'POST', { name: name.trim() || 'My place' })
      if (!result.workspace?.id || !result.workspace.name) throw new Error('The workspace could not be confirmed. Retry when the service is available.')
      location.replace('/setup?onboarding=1#cameras')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create your workspace. Try again.')
      creating.current = false
      setBusy(false)
    }
  }
  return <main className="mh-app ws-app">
    <header className="mh-header"><a href="/" aria-label="NIVRA home"><Brand /></a><a className="ws-devices" href="/mobile">Use this phone</a></header>
    <div className="ws-shell">
      <section className="ws-start" aria-labelledby="ws-title"><div className="ws-welcome-mark" aria-hidden><Brand compact /></div><h1 id="ws-title">Your cameras. One screen.</h1><p>Start here on your computer. Connect each phone with a QR.</p>
        {member ? <div className="ws-existing"><h2>{member.role === 'guard' ? 'Your guard screen is ready.' : 'Your cameras are ready.'}</h2><a href={member.role === 'guard' ? '/guard' : '/wall'}>Open {member.role === 'guard' ? 'guard screen' : 'camera wall'} <ArrowRight aria-hidden /></a></div> : <form onSubmit={create} className="ws-form"><button type="submit" disabled={checking || busy || !fresh}>{busy ? 'Getting ready…' : checking ? 'Just a moment…' : 'Get started'}<ArrowRight aria-hidden /></button><details className="ws-optional-name"><summary>Name your place (optional)</summary><label htmlFor="ws-site-name">Place name</label><input id="ws-site-name" value={name} onChange={event => setName(event.target.value)} maxLength={60} placeholder="My place" autoComplete="organization" /></details></form>}
        {checking && <p className="ws-status" role="status">Looking for your saved place…</p>}
        {error && <div className="ws-error"><p role="alert">{error}</p>{!fresh && <button type="button" onClick={() => setAttempt(value => value + 1)} disabled={checking}>Retry connection</button>}</div>}
        <p className="ws-web-note">No downloads. Your phones use Safari or Chrome.</p><p className="ws-network-note">Keep internet on. Your hotspot’s mobile data works.</p>
        <details className="ws-browser-note"><summary>About your access</summary><p>This browser remembers your place. Clearing its cookies removes your access. Connect camera and guard phones with their own QR.</p></details>
      </section>
      <aside className="ws-path" aria-label="What happens next"><span><Camera aria-hidden /> Scan. Allow camera. Watch.</span><span><ShieldCheck aria-hidden /> Add guards when you’re ready.</span></aside>
    </div>
  </main>
}
