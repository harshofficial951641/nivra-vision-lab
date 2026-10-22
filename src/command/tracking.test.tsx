import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CameraLocation } from '../classroom/contracts'
import { CameraTile } from './CameraTile'
import { liveCameras, type WallCamera } from './model'
import { containedTrackBox, observedTracks, wallMotion, wallTracking } from './tracking'

const now = 100_000
const track = { id: 7, box: [.1, .2, .5, .8], ambiguous: true, observed: true }
const result = { timestampMs: 5000, evidenceTimestampMs: 5000, inferenceMs: 100, backend: 'camera-device' as const, tracks: [track], coverage: { observedPeople: 1, analyzedPeople: 1, excludedPeople: 0, status: 'limited', actionPeople: 0 } }
const camera: WallCamera = { id: 'c1', label: 'CAM-01', name: 'Entrance', floorId: null, slot: null, sample: false, status: 'live', analysis: 'current', compute: 'device', image: 'blob:actual-frame', fps: 10, people: 1, result, generation: 'g1', preview: { received: now, timestampMs: 5050, width: 300, height: 600, generation: 'g1' } }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('real wall tracking', () => {
  it('keeps fast motion diagnostics independent of the crowd skeleton source frame', () => {
    const fast = { ...result, timestampMs: 5300, inferenceMs: 90, conflict: { status: 'limited', explanation: 'One person is visible. A second person is required to assess an interaction.' } }
    const source = { ...camera, motionResult: fast }
    expect(wallTracking(source, now).tracks).toEqual([track])
    expect(wallMotion(source)).toMatchObject({ label: 'Fast motion limited · 1 person · 90 ms', limited: true })
    render(<CameraTile camera={source} events={[]} now={now} size="hero" />)
    expect(screen.getByText('1 person · Motion check limited')).toBeVisible()
    expect(wallMotion({ ...source, status: 'offline' })).toBeNull()
    expect(wallMotion({ ...source, sample: true })).toBeNull()
  })
  it('preserves source results and preview dimensions when mapping live cameras', () => {
    const source = { id: 'c1', name: 'Entrance', building: 'A', floor: '1', feed: 'live', analysis: 'current', compute: 'device', generation: 'g1', result, deviceStatus: { state: 'ready', delegate: 'GPU', detail: 'Device ready' } } as CameraLocation
    const preview = { url: 'blob:frame', received: now, timestampMs: 5050, width: 300, height: 600, generation: 'g1' }
    const mapped = liveCameras([source], new Map(), { c1: preview }, {})[0]
    expect(mapped.result).toBe(result)
    expect(mapped.preview).toBe(preview)
    expect(mapped.deviceStatus?.state).toBe('ready')
    expect(wallTracking(mapped, now).tracks).toEqual([track])
  })
  it('keeps the latest video moving while slow analysis retains a separate review frame', () => {
    const source = { id: 'c1', name: 'Entrance', feed: 'live', analysis: 'current', compute: 'pc', generation: 'g1', result: { ...result, inferenceMs: 1700 } } as CameraLocation
    const live = { url: 'blob:latest', received: now, timestampMs: 6800, width: 300, height: 600, generation: 'g1' }
    const analyzed = { ...live, url: 'blob:review-source', timestampMs: 5000, received: now - 1800, analysisFrame: true }
    const mapped = liveCameras([source], new Map(), { c1: live }, {}, { c1: analyzed })[0]
    expect(mapped.image).toBe('blob:latest')
    expect(mapped.preview).toBe(live)
    expect(mapped.analysisPreview).toBe(analyzed)
    expect(wallTracking(mapped, now)).toMatchObject({ tracks: [], poses: [], label: 'AI delayed · boxes hidden' })
    expect(liveCameras([source], new Map(), {}, {}, { c1: analyzed })[0].image).toBeNull()
    expect(liveCameras([source], new Map(), { c1: live }, {}, { c1: { ...analyzed, generation: 'previous-session' } })[0].analysisPreview).toBeUndefined()
  })
  it('draws boxes and skeletons only within the source-frame matching tolerance', () => {
    expect(wallTracking({ ...camera, preview: { ...camera.preview, timestampMs: 5180 } }, now).tracks).toEqual([track])
    const ahead = wallTracking({ ...camera, preview: { ...camera.preview, timestampMs: 5181 } }, now)
    expect(ahead.tracks).toEqual([])
    expect(ahead.poses).toEqual([])
  })
  it('positions portrait boxes inside the actual contained image, including side bars', () => {
    const portrait = containedTrackBox(track.box, 300, 600, 1000, 600)
    expect(portrait).toMatchObject({ left: 380, top: 120, width: 120 })
    expect(portrait?.height).toBeCloseTo(360)
    const wide = containedTrackBox([0, 0, 1, 1], 1920, 1080, 600, 1000)
    expect(wide).toEqual({ left: 0, top: 331.25, width: 600, height: 337.5 })
  })
  it('shows actual observed track IDs in the fullscreen camera path and separates AI from Live', () => {
    vi.stubGlobal('ResizeObserver', class { callback: ResizeObserverCallback; constructor(callback: ResizeObserverCallback) { this.callback = callback } observe() { this.callback([{ contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver) } disconnect() {} })
    const view = render(<CameraTile camera={camera} events={[]} now={now} size="hero" />)
    expect(screen.getByText('Live')).toBeInTheDocument()
    expect(screen.getByText('1 person · Motion check limited')).toBeInTheDocument()
    const box = screen.getByText('Track 7 · tentative').parentElement!
    expect(box).toHaveStyle({ left: '380px', top: '120px', width: '120px' })
    expect(box).toHaveClass('is-tentative')
    view.rerender(<CameraTile camera={camera} events={[]} now={now + 3000} size="hero" />)
    expect(screen.queryByText('Track 7 · tentative')).not.toBeInTheDocument()
    expect(screen.getByText('Video is ahead. Markings paused.')).toBeInTheDocument()
  })
  it.each([
    { preview: { ...camera.preview, timestampMs: 7001 } },
    { preview: { ...camera.preview, generation: 'old-stream' } },
    { analysis: 'waiting' as const },
    { sample: true },
    { status: 'offline' as const },
  ])('never draws a stale, mismatched, or sample result (%j)', patch => {
    expect(wallTracking({ ...camera, ...patch }, now).tracks).toEqual([])
  })
  it('filters predicted and malformed boxes instead of inventing tracking', () => {
    expect(observedTracks([{ ...track, observed: false }, { ...track, box: [0, 0, -1, 1] }, { ...track, box: [0, 0, NaN, 1] }])).toEqual([])
    expect(wallTracking({ ...camera, result: { ...result, tracks: [] } }, now).label).toBe('AI sees 1 · no usable tracks')
  })
  it('shows the motion-analysis subset separately from classroom person tracking', () => {
    const tracks = Array.from({ length: 24 }, (_, id) => ({ ...track, id }))
    const state = wallTracking({ ...camera, result: { ...result, tracks, coverage: { ...result.coverage, observedPeople: 24, analyzedPeople: 10 }, conflict: { status: 'limited', explanation: 'Some tracked people have no usable pose.' } } }, now)
    expect(state.tracks).toHaveLength(24)
    expect(state.label).toBe('AI tracking · 24 people · motion 10/24')
    expect(state.detail).toBe('Some tracked people have no usable pose.')
  })
  it('draws delayed skeletons on their matching analyzed frame with an explicit age', () => {
    const delayed = { ...camera, result: { ...result, inferenceMs: 1700 }, preview: { ...camera.preview, received: now - 2000, analysisFrame: true } }
    expect(wallTracking(delayed, now).tracks).toEqual([track])
    expect(wallTracking(delayed, now).label).toBe('AI frame · 2.0s ago · 1 person · motion slow')
    expect(wallTracking(delayed, now + 4001).tracks).toEqual([])
    expect(wallTracking({ ...delayed, preview: { ...delayed.preview, timestampMs: 5200 } }, now).tracks).toEqual([])
  })
  it('exposes loading and error even when a live image is available', () => {
    expect(wallTracking({ ...camera, deviceStatus: { state: 'loading', delegate: null, detail: 'Loading model' } }, now).label).toBe('AI loading')
    const state = wallTracking({ ...camera, deviceStatus: { state: 'error', delegate: null, detail: 'GPU failed' } }, now)
    expect(state.label).toBe('AI error')
    expect(state.detail).toBe('GPU failed')
    expect(state.tracks).toEqual([])
  })
})
