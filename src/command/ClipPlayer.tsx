import { useEffect, useRef, useState } from 'react'
import { ArrowClockwise, Pause, Play, SkipForward } from '@phosphor-icons/react'

export interface PlayerFrame {
  src: string | Blob
  /** Epoch ms. */
  at: number
}

interface Props {
  label: string
  frames: PlayerFrame[]
  startAt: number
  peakAt: number
  endAt: number
  complete: boolean
  note?: string
}

const fmt = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export function ClipPlayer({ label, frames, startAt, peakAt, endAt, complete, note }: Props) {
  const duration = endAt - startAt
  const [position, setPosition] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [loop, setLoop] = useState(true)
  const urls = useRef(new Map<Blob, string>())
  useEffect(() => {
    const cache = urls.current
    return () => {
      cache.forEach((url) => URL.revokeObjectURL(url))
      cache.clear()
    }
  }, [])
  const source = (frame: PlayerFrame) => {
    if (typeof frame.src === 'string') return frame.src
    let url = urls.current.get(frame.src)
    if (!url) {
      url = URL.createObjectURL(frame.src)
      urls.current.set(frame.src, url)
    }
    return url
  }

  const available = complete ? duration : Math.max(0, (frames.at(-1)?.at ?? startAt) - startAt)
  const latest = useRef({ available, loop, speed })
  useEffect(() => {
    latest.current = { available, loop, speed }
  })
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let last = performance.now()
    const step = (now: number) => {
      const { available: end, loop: repeat, speed: rate } = latest.current
      setPosition((old) => {
        const next = old + (now - last) * rate
        if (next < end) return next
        if (repeat && end > 0 && complete) return 0
        return end
      })
      last = now
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [playing, complete])

  const offsets = frames.map((f) => f.at - startAt)
  let index = -1
  for (let i = 0; i < offsets.length; i++) if (offsets[i] <= position) index = i
  const current = frames[Math.max(0, index)]
  const stepFrame = () => {
    setPlaying(false)
    const next = offsets.find((offset) => offset > position + 1)
    setPosition(next ?? 0)
  }
  const peak = ((peakAt - startAt) / duration) * 100

  return (
    <div className="cm-player">
      <div className="cm-player-screen">
        {current ? (
          <img src={source(current)} alt={`Clip frame from ${label}`} />
        ) : (
          <div className="cm-feed-empty">
            <span>No footage was buffered for this incident in this browser.</span>
          </div>
        )}
        <span className="cm-player-chip">CLIP · {label} · {Math.round(duration / 1000)} s</span>
        {!complete && (
          <span className="cm-player-chip cm-player-chip--wait" role="status">
            Recording the {Math.round((endAt - startAt - (peakAt - startAt)) / 1000)} s after detection…
          </span>
        )}
      </div>
      <div className="cm-scrub">
        <span>{fmt(position)}</span>
        <div className="cm-scrub-track">
          <input
            type="range"
            min={0}
            max={duration}
            step={100}
            value={Math.min(position, duration)}
            aria-label="Clip position"
            aria-valuetext={`${fmt(position)} of ${fmt(duration)}`}
            onChange={(event) => {
              setPlaying(false)
              setPosition(Math.min(Number(event.target.value), available))
            }}
          />
          <span className="cm-peak" style={{ left: `${peak}%` }} aria-hidden>
            <b>Signal peak</b>
          </span>
        </div>
        <span>{fmt(duration)}</span>
      </div>
      <div className="cm-player-controls">
        <button type="button" className="cm-btn cm-btn--quiet" onClick={() => setPlaying((p) => !p)}>
          {playing ? <Pause aria-hidden /> : <Play aria-hidden />} {playing ? 'Pause' : 'Play'}
        </button>
        <button
          type="button"
          className="cm-btn cm-btn--quiet"
          aria-pressed={speed === 0.5}
          onClick={() => setSpeed((s) => (s === 1 ? 0.5 : 1))}
        >
          {speed === 1 ? '1x' : '0.5x'}
        </button>
        <button type="button" className="cm-btn cm-btn--quiet" onClick={stepFrame}>
          <SkipForward aria-hidden /> Frame
        </button>
        <button type="button" className="cm-btn cm-btn--quiet" aria-pressed={loop} onClick={() => setLoop((l) => !l)}>
          <ArrowClockwise aria-hidden /> Loop
        </button>
      </div>
      {note && <p className="cm-muted cm-player-note">{note}</p>}
    </div>
  )
}
