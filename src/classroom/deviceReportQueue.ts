type Event = { id: string; occurredAtMs: number; detail: string }
type Report = { timestampMs: number; events: Event[] }

/** Coalesce frames without dropping distinct incidents or exceeding socket limits. */
export class DeviceReportQueue<T extends Report> {
  private latest: T | null = null
  private pending = new Map<string, Event>()
  private seen = new Map<string, number>()
  private lastSent = -Infinity
  private lastSource = -Infinity
  private intervalMs: number
  constructor(intervalMs: number) { this.intervalMs = intervalMs }

  push(report: T) {
    if (report.timestampMs <= this.lastSource) return
    this.lastSource = report.timestampMs
    for (const [id, at] of this.seen) if (report.timestampMs - at > 5000) this.seen.delete(id)
    for (const [id, event] of this.pending) if (report.timestampMs - event.occurredAtMs > 5000) this.pending.delete(id)
    for (const event of report.events) {
      if (this.seen.has(event.id)) continue
      this.seen.set(event.id, event.occurredAtMs)
      this.pending.set(event.id, event)
    }
    while (this.pending.size > 32) this.pending.delete(this.pending.keys().next().value!)
    while (this.seen.size > 64) this.seen.delete(this.seen.keys().next().value!)
    this.latest = report
  }

  take(now: number): T | null {
    if (!this.latest || now - this.lastSent < this.intervalMs) return null
    const events = [...this.pending.values()].slice(0, 2)
    for (const event of events) this.pending.delete(event.id)
    const report = { ...this.latest, events }
    this.latest = null
    this.lastSent = now
    return report
  }

  clear() { this.latest = null; this.pending.clear(); this.seen.clear() }
}
