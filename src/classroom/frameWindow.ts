/** Bounded transport window: capture current frames without waiting one RTT each. */
export class FrameWindow {
  private pending = new Map<number, { sentAt: number; bytes: number }>()
  private bytes = 0

  canSend(now: number, bufferedBytes: number, nextBytes = 0) {
    const oldest = this.pending.values().next().value
    return (
      this.pending.size < 8 &&
      (this.bytes + nextBytes <= 768 * 1024 ||
        (this.pending.size === 0 && nextBytes <= 1500000)) &&
      (bufferedBytes === 0 || bufferedBytes + nextBytes <= 256 * 1024) &&
      (!oldest || now - oldest.sentAt < 750)
    )
  }

  sent(timestamp: number, now: number, bytes: number) {
    this.pending.set(timestamp, { sentAt: now, bytes })
    this.bytes += bytes
  }

  acknowledge(timestamp: number) {
    const frame = this.pending.get(timestamp)
    if (!frame) return false
    this.bytes -= frame.bytes
    this.pending.delete(timestamp)
    return true
  }

  timedOut(now: number) {
    const oldest = this.pending.values().next().value
    return !!oldest && now - oldest.sentAt > 3000
  }
}
