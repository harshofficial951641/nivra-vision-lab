// Sample workspace shared between tabs on one computer (Command ?demo=1 and
// Guard ?demo=1). Generated imagery and illustrative records only.
import type { Incident } from '../classroom/contracts'
import { CAMERA_SLOTS, SITE } from './siteMap'
import {
  applyGuardAction,
  applyReview,
  type GuardAction,
  type ReviewAction,
  type ReviewPayload,
} from './model'

export interface SampleState {
  version: 1
  events: Incident[]
}
const KEY = 'nivra.sample-command.v1'
const CHANNEL = 'nivra-sample-command'
export const SAMPLE_SIGNALS = [
  'Distance closed 3 times in 6 s',
  'Fast arm movement toward upper body',
  '3 bystanders converged',
].join('\n')

const slotName = (id: string) => CAMERA_SLOTS.find((s) => s.id === id)?.name ?? id
const at = (base: number, seconds: number) => base + seconds * 1000

function record(
  cameraId: string,
  minutesAgo: number,
  now: number,
  outcome:
    | { kind: 'false'; reason: NonNullable<Incident['reason']>; review: number; decide: number }
    | { kind: 'confirmed'; guard: string; review: number; decide: number; ack: number; scene: number; clear: number },
): Incident {
  const received = now - minutesAgo * 60_000
  const base: Incident = {
    id: `sample-${cameraId}-${minutesAgo}`,
    camera_id: cameraId,
    camera_name: slotName(cameraId),
    location: `${SITE.name} · ${SITE.floor}`,
    received_at: received,
    source_ms: 0,
    evidence_ms: 0,
    model: 'sample',
    detail: SAMPLE_SIGNALS,
    status: 'resolved',
    revision: 4,
    updated_at: received,
    reviewed_at: at(received, outcome.review),
    decided_at: at(received, outcome.decide),
  }
  if (outcome.kind === 'false')
    return { ...base, decision: 'false_alarm', reason: outcome.reason, updated_at: at(received, outcome.decide) }
  return {
    ...base,
    decision: 'confirmed',
    guard: outcome.guard,
    alerted_at: at(received, outcome.decide),
    guard_ack_at: at(received, outcome.ack),
    on_scene_at: at(received, outcome.scene),
    updated_at: at(received, outcome.clear),
  }
}

export function seedState(now = Date.now()): SampleState {
  return {
    version: 1,
    events: [
      record('cam-10', 18, now, { kind: 'confirmed', guard: 'G3', review: 1, decide: 8, ack: 12, scene: 40, clear: 190 }),
      record('cam-01', 31, now, { kind: 'false', reason: 'other', review: 2, decide: 7 }),
      record('cam-06', 47, now, { kind: 'false', reason: 'camera_glitch', review: 4, decide: 10 }),
      record('cam-08', 64, now, { kind: 'confirmed', guard: 'G5', review: 2, decide: 11, ack: 16, scene: 48, clear: 240 }),
      record('cam-02', 80, now, { kind: 'false', reason: 'greeting', review: 2, decide: 9 }),
      record('cam-07', 92, now, { kind: 'false', reason: 'play_sport', review: 3, decide: 14 }),
    ],
  }
}

type Listener = () => void
export class SampleStore {
  private state: SampleState
  private listeners = new Set<Listener>()
  private channel: BroadcastChannel | null = null
  private storage: Storage | null

  constructor(storage: Storage | null = globalThis.localStorage ?? null) {
    this.storage = storage
    this.state = this.read() ?? seedState()
    if (typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel(CHANNEL)
      this.channel.onmessage = (message) => {
        if (message.data?.version === 1) this.set(message.data, false)
      }
    }
  }

  private read(): SampleState | null {
    try {
      const value = JSON.parse(this.storage?.getItem(KEY) ?? 'null')
      return value?.version === 1 && Array.isArray(value.events) ? value : null
    } catch {
      return null
    }
  }

  private set(state: SampleState, share = true) {
    this.state = state
    if (share) {
      try {
        this.storage?.setItem(KEY, JSON.stringify(state))
      } catch {
        // Storage full or blocked: the tab still works on its own.
      }
      this.channel?.postMessage(state)
    }
    this.listeners.forEach((listener) => listener())
  }

  getState = () => this.state
  subscribe = (listener: Listener) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private update(id: string, change: (event: Incident) => Incident) {
    const event = this.state.events.find((e) => e.id === id)
    if (!event) throw new Error('Sample incident not found.')
    const next = change(event)
    if (next !== event)
      this.set({ ...this.state, events: this.state.events.map((e) => (e.id === id ? next : e)) })
  }

  review(id: string, action: ReviewAction, payload: ReviewPayload = {}) {
    this.update(id, (event) => applyReview(event, action, payload, Date.now()))
  }

  guardAction(id: string, action: GuardAction) {
    this.update(id, (event) => applyGuardAction(event, action, Date.now()))
  }

  runIncident(cameraId = 'cam-04') {
    const now = Date.now()
    const event: Incident = {
      id: `sample-live-${now}`,
      camera_id: cameraId,
      camera_name: slotName(cameraId),
      location: `${SITE.name} · ${SITE.floor}`,
      received_at: now,
      source_ms: 0,
      evidence_ms: 0,
      model: 'sample',
      detail: SAMPLE_SIGNALS,
      status: 'open',
      revision: 0,
      updated_at: now,
    }
    this.set({ ...this.state, events: [event, ...this.state.events] })
    return event
  }

  reset() {
    this.set(seedState())
  }

  dispose() {
    this.channel?.close()
    this.listeners.clear()
  }
}

let shared: SampleStore | null = null
export const sampleStore = () => (shared ??= new SampleStore())
