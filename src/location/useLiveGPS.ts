import { useEffect, useRef, useState } from 'react'
import type { GPSLocation } from './gps'
import { watchGPS } from './watchGPS'

export function useLiveGPS(enabled: boolean, save: (point: GPSLocation) => Promise<unknown>) {
  const saveRef = useRef(save)
  const writes = useRef<Promise<unknown>>(Promise.resolve())
  saveRef.current = save
  const [point, setPoint] = useState<GPSLocation | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!enabled) return
    let active = true
    setError('')
    const clock = setInterval(() => setNow(Date.now()), 1000)
    const stop = watchGPS({
      save: fix => {
        const next = writes.current.catch(() => undefined).then(() => active ? saveRef.current(fix) : undefined)
        writes.current = next
        return next
      },
      onSaved: fix => { setPoint(fix); setNow(Date.now()); setError('') },
      onError: setError,
    })
    return () => { active = false; clearInterval(clock); stop() }
  }, [enabled, attempt])
  return { point, error, retry: () => setAttempt(value => value + 1), age: point ? Math.max(0, Math.floor((now - point.capturedAt) / 1000)) : null }
}
