import { useId, useRef, useState } from 'react'
import { api, type PoliceContactRecord } from '../classroom/contracts'
import './police.css'

function policeNumber(value: unknown): string {
  return typeof value === 'string' && value.length > 0 && !/[^0-9+*]/.test(value) ? value : '112'
}

export function PoliceContactStatus({ police }: { police?: PoliceContactRecord | null }) {
  if (!police) return null
  const by = police.by.startsWith('guard:') ? police.by.slice(6) : police.by
  const clock = new Date(police.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  return <span className="police-status">Police contacted ({police.method}) by {by} at {clock}</span>
}

interface Props {
  incidentId: string
  cameraName: string
  location: string
  police?: PoliceContactRecord | null
  role: 'guard' | 'reviewer'
  sample?: boolean
}

export function PoliceContact({ incidentId, cameraName, location, police, role, sample = false }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [error, setError] = useState(false)
  const [recorded, setRecorded] = useState<PoliceContactRecord | null>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const controls = useId()
  const number = policeNumber(import.meta.env.VITE_NIVRA_POLICE_NUMBER)
  const message = `NIVRA alert: possible physical conflict at ${cameraName}, ${location}. Please send police.`
  const buttonClass = role === 'guard' ? 'gd-btn gd-btn--outline' : 'cm-btn'
  const latest = recorded && (!police || recorded.at > police.at) ? recorded : police
  const log = (method: 'call' | 'text') => {
    setError(false)
    // Recording must not await or cancel the OS dial/message action.
    void api<{ police: PoliceContactRecord }>(
      `${role === 'guard' ? '/guard' : ''}/events/${encodeURIComponent(incidentId)}/police`,
      'POST', { method }, { keepalive: true },
    ).then(result => setRecorded(result.police)).catch(() => setError(true))
  }
  return <div className="police-contact" role="group" aria-label="Contact police">
    <PoliceContactStatus police={latest} />
    {sample ? <span className="police-status">Police contact unavailable in sample mode.</span> : <>
      <button ref={trigger} type="button" className={buttonClass} aria-expanded={expanded} aria-controls={controls} onClick={() => setExpanded(value => !value)}>Police</button>
      {expanded && <div id={controls} className="police-actions" role="group" aria-label="Confirm police contact">
        <a className={buttonClass} href={`tel:${number}`} onClick={() => log('call')}>Call {number}</a>
        <a className={buttonClass} href={`sms:${number}?&body=${encodeURIComponent(message)}`} onClick={() => log('text')}>Text police</a>
        <button type="button" className={buttonClass} onClick={() => { setExpanded(false); trigger.current?.focus() }}>Cancel</button>
      </div>}
    </>}
    {error && <p role="alert">Could not record police contact</p>}
  </div>
}
