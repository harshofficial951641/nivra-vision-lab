// A single quiet note, unlocked only by the wall's sound button.
export class AlertPing {
  private context: AudioContext | null = null
  private notes = new Set<OscillatorNode>()
  private disposed = false
  private generation = 0

  async prime(): Promise<boolean> {
    if (this.disposed) return false
    try {
      const Audio = window.AudioContext ?? (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Audio) return false
      this.context ??= new Audio()
      if (this.context.state !== 'running') await this.context.resume()
      return !this.disposed && this.context.state === 'running'
    } catch { return false }
  }

  async play(): Promise<void> {
    const generation = this.generation
    if (!await this.prime() || generation !== this.generation || !this.context || this.notes.size > 0) return
    const context = this.context
    const note = context.createOscillator()
    const gain = context.createGain()
    note.type = 'sine'
    note.frequency.value = 740
    gain.gain.setValueAtTime(0, context.currentTime)
    gain.gain.linearRampToValueAtTime(.08, context.currentTime + .012)
    gain.gain.exponentialRampToValueAtTime(.001, context.currentTime + .15)
    note.connect(gain)
    gain.connect(context.destination)
    this.notes.add(note)
    note.onended = () => { this.notes.delete(note); note.disconnect(); gain.disconnect() }
    note.start()
    note.stop(context.currentTime + .16)
  }

  stop(): void {
    this.generation++
    for (const note of this.notes) { try { note.stop() } catch { /* Already ended. */ } }
    this.notes.clear()
  }

  dispose(): void {
    this.disposed = true
    this.stop()
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => undefined)
    this.context = null
  }
}
