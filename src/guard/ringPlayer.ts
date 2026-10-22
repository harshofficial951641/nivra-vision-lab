// Loud phone-style ring for guard alerts, generated with Web Audio (no audio
// files). Browsers only allow sound after a tap, so prime() must run from the
// guard's "Start shift" tap.

type AudioWindow = Window & { webkitAudioContext?: typeof AudioContext }

export const RING_MS = 4000

export class RingPlayer {
  private context: AudioContext | null = null
  private master: GainNode | null = null
  private nodes: OscillatorNode[] = []
  private timer = 0

  get ready() {
    return this.context?.state === 'running'
  }

  /** Call from a user gesture. Returns false when audio is blocked or missing. */
  async prime() {
    const Context = window.AudioContext ?? (window as AudioWindow).webkitAudioContext
    if (!Context) return false
    this.context ??= new Context()
    if (this.context.state !== 'running') await this.context.resume().catch(() => undefined)
    if (!this.master && this.context) {
      const compressor = this.context.createDynamicsCompressor()
      compressor.threshold.value = -6
      compressor.ratio.value = 4
      this.master = this.context.createGain()
      this.master.gain.value = 0.9
      this.master.connect(compressor).connect(this.context.destination)
    }
    return this.ready
  }

  /**
   * Classic two-tone trill: 0.8 s bursts warbling 20 times a second between
   * two pitches, 0.4 s gaps, for `durationMs`. Vibrates in step when supported.
   */
  ring(durationMs = RING_MS) {
    this.stop()
    navigator.vibrate?.(pattern(durationMs))
    const context = this.context
    if (!context || !this.master || context.state !== 'running') return false
    const start = context.currentTime + 0.02
    for (let burst = 0; burst * 1.2 < durationMs / 1000; burst++) {
      const t0 = start + burst * 1.2
      const end = Math.min(t0 + 0.8, start + durationMs / 1000)
      for (const [frequency, level] of [
        [1046, 0.55],
        [1318, 0.45],
      ] as const) {
        const osc = context.createOscillator()
        const gain = context.createGain()
        osc.type = 'square'
        osc.frequency.value = frequency
        gain.gain.value = 0
        for (let t = t0, on = frequency === 1046; t < end; t += 0.05, on = !on) {
          gain.gain.setValueAtTime(on ? level : 0, t)
        }
        gain.gain.setValueAtTime(0, end)
        osc.connect(gain).connect(this.master)
        osc.start(t0)
        osc.stop(end + 0.02)
        this.nodes.push(osc)
      }
    }
    this.timer = window.setTimeout(() => {
      this.nodes = []
    }, durationMs + 200)
    return true
  }

  stop() {
    clearTimeout(this.timer)
    navigator.vibrate?.(0)
    for (const node of this.nodes) {
      try {
        node.stop()
      } catch {
        // Already stopped.
      }
    }
    this.nodes = []
  }

  dispose() {
    this.stop()
    void this.context?.close()
    this.context = null
    this.master = null
  }
}

export function pattern(durationMs: number) {
  const steps: number[] = []
  for (let t = 0; t < durationMs; t += 1200) steps.push(Math.min(800, durationMs - t), 400)
  return steps
}

/** Ring now, then every 15 s, at most four times, until acknowledged. */
export const RING_REPEAT_MS = 15_000
export const RING_MAX = 4
export function shouldRing(alertedAt: number, rings: number, lastRing: number, now: number) {
  if (rings >= RING_MAX) return false
  if (rings === 0) return now >= alertedAt
  return now - lastRing >= RING_REPEAT_MS
}
