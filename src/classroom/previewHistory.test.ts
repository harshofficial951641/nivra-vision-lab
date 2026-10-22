import { describe, expect, it, vi } from 'vitest'
import { PreviewHistory } from './previewHistory'
import { liveCameras } from '../command/model'
import type { CameraLocation } from './contracts'
const meta = (timestampMs: number, generation = 'g1') => ({ timestampMs, generation, width: 640, height: 360 })
const jpeg = new Blob(['real JPEG bytes'], { type: 'image/jpeg' })
function buffer() {
  let count = 0
  const revoke = vi.fn()
  const history = new PreviewHistory(() => `blob:history-${++count}`, revoke)
  return { history, revoke, created: () => count }
}
describe('Analyzed source-frame history', () => {
  it('finds the nearest source frame within180ms only in the exact stream generation', () => {
    const { history } = buffer()
    history.add('c1', meta(100), jpeg, 1000)
    history.add('c1', meta(400), jpeg, 1300)
    expect(history.select('c1', 'g1', 260, 2000)).toMatchObject({ timestampMs: 400, analysisFrame: true })
    expect(history.select('c1', 'g1', 581, 2000)).toBeUndefined()
    expect(history.select('c1', 'old-stream', 100, 2000)).toBeUndefined()
  })
  it('keeps a six-second window sampled from a smooth12fps feed and bounds owned URLs', () => {
    const { history, revoke, created } = buffer()
    for (let time = 0; time <= 6000; time += 84) history.add('c1', meta(time), jpeg, 10000 + time)
    expect(history.select('c1', 'g1', 100, 16000)).toMatchObject({ timestampMs: 0 })
    expect(history.select('c1', 'g1', 4200, 16000)?.timestampMs).toBeCloseTo(4284, 0)
    expect(created() - revoke.mock.calls.length).toBeLessThanOrEqual(32)
    history.select('c1', 'g1', 0, 16001)
    expect(revoke).toHaveBeenCalledWith('blob:history-1')
    history.clear()
    expect(revoke).toHaveBeenCalledTimes(created())
    expect(new Set(revoke.mock.calls.map(call => call[0])).size).toBe(created())
  })
  it('releases old generations, removed cameras, and every remaining URL exactly once', () => {
    const { history, revoke, created } = buffer()
    history.add('c1', meta(100), jpeg, 1000)
    history.add('c1', meta(200, 'g2'), jpeg, 1100)
    expect(revoke).toHaveBeenCalledWith('blob:history-1')
    expect(history.select('c1', 'g1', 100, 1100)).toBeUndefined()
    history.add('c2', meta(200), jpeg, 1100)
    history.retain(new Map([['c1', 'g2']]))
    expect(revoke).toHaveBeenCalledWith('blob:history-3')
    history.clear()
    history.clear()
    expect(revoke).toHaveBeenCalledTimes(created())
  })
  it('keeps the live JPEG on the wall and retains aligned analysis separately for review', () => {
    const source = { id: 'c1', name: 'Room', building: 'A', floor: '1', feed: 'live', generation: 'g1', result: { timestampMs: 100, inferenceMs: 1700 } } as CameraLocation
    const current = { url: 'blob:live', ...meta(1800), received: 11800 }
    const aligned = { url: 'blob:analyzed', ...meta(90), received: 10090, analysisFrame: true }
    const make = (camera = source, selected = aligned) => liveCameras([camera], new Map(), { c1: current }, {}, { c1: selected })[0]
    expect(make()).toMatchObject({ image: 'blob:live', preview: current, analysisPreview: aligned })
    expect(liveCameras([source], new Map(), { c1: current }, {})[0].image).toBe('blob:live')
    expect(make({ ...source, result: { ...source.result!, inferenceMs: 500 } }).image).toBe('blob:live')
    expect(make(source, { ...aligned, generation: 'old' }).image).toBe('blob:live')
    expect(make(source, { ...aligned, generation: 'old' }).analysisPreview).toBeUndefined()
    expect(make(source, { ...aligned, timestampMs: 281 }).image).toBe('blob:live')
    expect(make(source, { ...aligned, timestampMs: 281 }).analysisPreview).toBeUndefined()
  })
})
