import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { api, type Incident } from '../classroom/contracts'
import { useClassroom } from '../classroom/useClassroom'
import { ClipBuffer } from './clipBuffer'
import {
  liveCameras,
  liveGuards,
  needsDecision,
  sampleCameras,
  type ReviewAction,
  type ReviewPayload,
  type WallCamera,
} from './model'
import { sampleStore } from './sampleStore'
import { SAMPLE_FLOOR, SAMPLE_GUARDS, SITE, mapFloor } from './siteMap'
import type { MapFloor, WallGuard } from './types'

export interface CommandData {
  sample: boolean
  connection: 'connecting' | 'connected' | 'disconnected'
  error: string
  service: 'ready' | 'loading' | 'error' | null
  runtime: { device?: string; personModel?: string; fightModel?: string } | null
  siteName: string
  floors: MapFloor[]
  cameras: WallCamera[]
  guards: WallGuard[]
  events: Incident[]
  clips: ClipBuffer | null
  review: (event: Incident, action: ReviewAction, payload?: ReviewPayload) => Promise<void>
  runSample: () => void
  resetSample: () => void
}

const noop = () => () => {}
const emptyState = () => null

export function useCommand(sample: boolean): CommandData {
  const store = sample ? sampleStore() : null
  const state = useSyncExternalStore(store?.subscribe ?? noop, store?.getState ?? emptyState)
  // Browser-side fallback clips for services that do not record clips yet.
  const clips = useRef<ClipBuffer | null>(null)
  if (!sample && !clips.current) clips.current = new ClipBuffer()
  const onFrame = useCallback((id: string, jpeg: Blob, at: number) => clips.current?.push(id, jpeg, at), [])
  const live = useClassroom(!sample, sample ? undefined : onFrame, true)
  const snapshot = live.snapshot

  // Analysis rate per camera from consecutive snapshot counters.
  const counters = useRef(new Map<string, { frames: number; at: number }>())
  const [fps, setFps] = useState<Record<string, number>>({})
  useEffect(() => {
    if (!snapshot) return
    const now = performance.now()
    const next: Record<string, number> = {}
    for (const camera of snapshot.cameras) {
      const previous = counters.current.get(camera.id)
      if (previous && now - previous.at >= 900 && camera.framesAnalyzed >= previous.frames) {
        next[camera.id] = Math.round(((camera.framesAnalyzed - previous.frames) / ((now - previous.at) / 1000)) * 10) / 10
        counters.current.set(camera.id, { frames: camera.framesAnalyzed, at: now })
      } else if (!previous) counters.current.set(camera.id, { frames: camera.framesAnalyzed, at: now })
    }
    if (Object.keys(next).length) setFps((old) => ({ ...old, ...next }))
  }, [snapshot])

  const known = useRef<Set<string> | null>(null)
  useEffect(() => {
    if (!snapshot) return
    const ids = new Set(snapshot.events.map((e) => e.id))
    if (known.current)
      for (const event of snapshot.events)
        if (!known.current.has(event.id) && needsDecision(event))
          clips.current?.capture(event.id, event.camera_id, Date.now())
    known.current = ids
  }, [snapshot])

  const floors = useMemo(
    () =>
      sample
        ? [SAMPLE_FLOOR]
        : [...(snapshot?.floors ?? [])].sort((a, b) => a.order - b.order).map(mapFloor),
    [sample, snapshot?.floors],
  )
  const floorMap = useMemo(() => new Map(floors.map((f) => [f.id, f])), [floors])
  const cameras = useMemo(
    () => (sample ? sampleCameras() : liveCameras(snapshot?.cameras ?? [], floorMap, live.previews, fps)),
    [sample, snapshot?.cameras, floorMap, live.previews, fps],
  )
  const guards = useMemo(
    () => (sample ? SAMPLE_GUARDS : liveGuards(snapshot?.guards ?? [], floorMap)),
    [sample, snapshot?.guards, floorMap],
  )

  const review = useCallback(
    async (event: Incident, action: ReviewAction, payload: ReviewPayload = {}) => {
      if (store) {
        store.review(event.id, action, payload)
        return
      }
      await api(`/events/${event.id}/review`, 'POST', {
        action,
        revision: event.revision,
        ...(payload.reason ? { reason: payload.reason } : {}),
        ...(payload.note?.trim() ? { note: payload.note.trim() } : {}),
        ...(payload.guard ? { guard: payload.guard } : {}),
      })
      if (action === 'dismiss' || action === 'clear') clips.current?.release(event.id)
    },
    [store],
  )

  return {
    sample,
    connection: sample ? 'connected' : live.connection,
    error: sample ? '' : live.error,
    service: sample ? 'ready' : snapshot?.service ?? null,
    runtime: sample ? null : (snapshot?.runtime as CommandData['runtime']) ?? null,
    siteName: sample ? SITE.name : snapshot?.site?.name ?? 'NIVRA site',
    floors,
    cameras,
    guards,
    events: sample ? state?.events ?? [] : snapshot?.events ?? [],
    clips: clips.current,
    review,
    runSample: () => store?.runIncident(),
    resetSample: () => store?.reset(),
  }
}
