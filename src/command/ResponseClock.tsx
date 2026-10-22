import type { Incident } from '../classroom/contracts'
import { formatClock, responseSteps, type WallCamera } from './model'

export function ResponseClock({
  event,
  cameras,
}: {
  event: Incident | null
  cameras: WallCamera[]
}) {
  if (!event)
    return (
      <section className="cm-clock" aria-labelledby="clock-heading">
        <h2 id="clock-heading">Response clock</h2>
        <p className="cm-muted">No incidents in the last ten minutes. All quiet.</p>
      </section>
    )
  const camera = cameras.find((c) => c.id === event.camera_id)
  const steps = responseSteps(event, camera?.label ?? event.camera_name)
  return (
    <section className="cm-clock" aria-labelledby="clock-heading">
      <h2 id="clock-heading">Response clock</h2>
      <ol aria-live="polite">
        {steps.map((step) => (
          <li key={step.key} className={`is-${step.tone}`}>
            <i aria-hidden />
            <time>{step.at ? formatClock(step.at) : ''}</time>
            <span>{step.label}</span>
            {step.at && step.key !== 'detected' && (
              <small>+{Math.max(0, Math.round((step.at - event.received_at) / 1000))} s</small>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
