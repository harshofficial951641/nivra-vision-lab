import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowLeft, ArrowRight, Camera, QrCode, ShieldCheck, SquaresFour } from '@phosphor-icons/react'
import { Brand } from '../ui/Brand'
import { pairingDestination } from './pairingDestination'
import './mobile.css'

const roles = [
  { href: '/camera', tab: 'Camera', title: 'Make this a camera.', detail: 'Watch over your space with this phone.', action: 'Open camera', icon: Camera },
  { href: '/guard', tab: 'Guard', title: 'Ready for your shift?', detail: 'Get alerts and directions when help is needed.', action: 'Open guard', icon: ShieldCheck },
  { href: '/wall', tab: 'Watch', title: 'See your place.', detail: 'Your cameras and team, in one view.', action: 'Watch cameras', icon: SquaresFour },
]

export default function MobileHome() {
  const [active, setActive] = useState(0)
  const [pairURL, setPairURL] = useState('')
  const [error, setError] = useState('')
  const deck = useRef<HTMLDivElement>(null)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const help = useRef<HTMLDetailsElement>(null)
  const choose = (index: number, focus = false) => {
    const next = Math.max(0, Math.min(roles.length - 1, index))
    setActive(next)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    deck.current?.scrollTo({ left: next * deck.current.clientWidth, behavior: reduced ? 'instant' : 'smooth' })
    if (focus) tabs.current[next]?.focus()
  }
  const key = (event: KeyboardEvent, index: number) => {
    const next = event.key === 'ArrowRight' ? (index + 1) % roles.length : event.key === 'ArrowLeft' ? (index + roles.length - 1) % roles.length : event.key === 'Home' ? 0 : event.key === 'End' ? roles.length - 1 : null
    if (next !== null) { event.preventDefault(); choose(next, true) }
  }
  const followPair = (event: FormEvent) => {
    event.preventDefault()
    const destination = pairingDestination(pairURL, location.origin)
    if (!destination) { setError('Use a link from this NIVRA site, or ask the owner for a new QR.'); return }
    location.assign(destination)
  }
  return <main className="mh-app mh-launcher">
    <header className="mh-header"><a href="/mobile" aria-label="NIVRA home"><Brand /></a><button type="button" className="mh-help-link" onClick={() => { if (help.current) { help.current.open = true; help.current.scrollIntoView({ block: 'start' }); help.current.querySelector('summary')?.focus() } }}>Need help?</button></header>
    <section className="mh-picker" aria-labelledby="mh-title">
      <h1 id="mh-title">What’s this phone for?</h1>
      <div className="mh-tabs" role="tablist" aria-label="Choose what to do">
        {roles.map((role, index) => <button type="button" key={role.tab} id={`role-tab-${index}`} role="tab" aria-selected={active === index} aria-controls={`role-panel-${index}`} tabIndex={active === index ? 0 : -1} ref={element => { tabs.current[index] = element }} onClick={() => choose(index)} onKeyDown={event => key(event, index)}>{role.tab}</button>)}
      </div>
      <div className="mh-role-deck" ref={deck} onScroll={event => {
        const element = event.currentTarget
        if (element.clientWidth) setActive(Math.max(0, Math.min(roles.length - 1, Math.round(element.scrollLeft / element.clientWidth))))
      }}>
        {roles.map((role, index) => <section key={role.tab} id={`role-panel-${index}`} role="tabpanel" aria-labelledby={`role-tab-${index}`} aria-hidden={active !== index} className="mh-role-slide">
          <div className="mh-role-symbol"><role.icon aria-hidden weight="light" /></div>
          <h2>{role.title}</h2><p>{role.detail}</p>
          <a className="mh-primary" href={role.href} tabIndex={active === index ? 0 : -1}>{role.action}<ArrowRight aria-hidden /></a>
        </section>)}
      </div>
      <div className="mh-swipe-nav"><button type="button" aria-label="Previous role" disabled={active === 0} onClick={() => choose(active - 1)}><ArrowLeft aria-hidden /></button><p>Swipe to choose <span aria-hidden>·</span> {active + 1} / {roles.length}</p><button type="button" aria-label="Next role" disabled={active === roles.length - 1} onClick={() => choose(active + 1)}><ArrowRight aria-hidden /></button></div>
      <div className="mh-qr-tip"><QrCode aria-hidden /><p>Open Camera or Guard to scan a QR or enter your pairing code.</p></div>
      <a className="mh-place-link" href="/">Setting up a new place? <ArrowRight aria-hidden /></a>
    </section>
    <details className="mh-help" id="phone-help" ref={help}><summary>Help with your phone</summary><div>
      <h2>Keep NIVRA handy</h2><p>On iPhone, use Safari: Share → Add to Home Screen. On Android, use Chrome’s menu → Add to Home Screen.</p>
      <p>Keep this page open during use. Camera and location sharing pause when your phone puts the app to sleep.</p>
      <details><summary>Open a pairing link</summary><form onSubmit={followPair}><label htmlFor="mh-pair-link">Link from your owner</label><input id="mh-pair-link" type="url" value={pairURL} onChange={event => { setPairURL(event.target.value); setError('') }} autoComplete="off" spellCheck={false} required /><button className="mh-primary" type="submit">Open link <ArrowRight aria-hidden /></button></form>{error && <p className="mh-error" role="alert">{error}</p>}</details>
      <p>No download is needed. NIVRA works in this browser. Keep internet on; hotspot mobile data works.</p>
    </div></details>
  </main>
}
