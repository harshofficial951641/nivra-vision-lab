import { afterEach, describe, expect, it } from 'vitest'
import { SampleStore, seedState } from './sampleStore'

const stores: SampleStore[] = []
const make = (storage: Storage) => {
  const store = new SampleStore(storage)
  stores.push(store)
  return store
}
afterEach(() => {
  stores.splice(0).forEach((s) => s.dispose())
  localStorage.clear()
})

describe('SampleStore', () => {
  it('seeds a day of decided sample records', () => {
    const seed = seedState()
    expect(seed.events).toHaveLength(6)
    expect(seed.events.every((e) => e.decision)).toBe(true)
  })

  it('runs an incident and shares state with a second tab', async () => {
    const operator = make(localStorage)
    const guard = make(localStorage)
    const event = operator.runIncident('cam-04')
    operator.review(event.id, 'confirm', { guard: 'G2' })
    await new Promise((resolve) => setTimeout(resolve, 20))
    const seen = guard.getState().events.find((e) => e.id === event.id)
    expect(seen).toMatchObject({ decision: 'confirmed', guard: 'G2' })
    guard.guardAction(event.id, 'ack')
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(operator.getState().events.find((e) => e.id === event.id)?.guard_ack_at).toBeTypeOf('number')
  })

  it('keeps a closed undecided sample alert in history without inventing a judgment', () => {
    const store=make(localStorage)
    const event=store.runIncident('cam-04')
    store.review(event.id,'close',{})
    const closed=make(localStorage).getState().events.find(record=>record.id===event.id)!
    expect(closed.status).toBe('resolved')
    expect(closed.decision ?? null).toBeNull()
    expect(closed.reason ?? null).toBeNull()
    expect(closed.detail).toBe(event.detail)
  })

  it('restores from storage and resets', () => {
    const first = make(localStorage)
    first.runIncident()
    expect(make(localStorage).getState().events).toHaveLength(7)
    first.reset()
    expect(first.getState().events).toHaveLength(6)
  })
})
