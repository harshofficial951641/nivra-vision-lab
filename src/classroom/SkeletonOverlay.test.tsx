import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Skeletons } from './SkeletonOverlay'
import { skeletonGeometry, type CameraPose } from './skeletonGeometry'
import { CameraTile } from '../command/CameraTile'
import type { WallCamera } from '../command/model'

const pose = (): CameraPose => {
  const points: CameraPose = Array.from({ length: 33 }, () => null)
  points[11] = [.2, .3, 1]
  points[13] = [.3, .4, .8]
  points[15] = [.4, .5, .54]
  return points
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe('Observed camera skeletons', () => {
  it('fits actual portrait joints inside the image, preserving side bars', () => {
    render(<Skeletons poses={[pose()]} sourceWidth={300} sourceHeight={600} width={1000} height={600} />)
    const svg = screen.getByTestId('camera-skeletons')
    const shoulder = svg.querySelector('[data-joint="11"]')!
    expect(shoulder).toHaveAttribute('cx', '410')
    expect(shoulder).toHaveAttribute('cy', '180')
    const bone = svg.querySelector('[data-bone="11-13"]')!
    expect(bone).toHaveAttribute('x1', '410')
    expect(bone).toHaveAttribute('x2', '440')
    expect(svg.querySelector('[data-joint="15"]')).toBeNull()
    expect(svg.querySelector('[data-bone="13-15"]')).toBeNull()
    expect(svg.querySelectorAll('circle')).toHaveLength(2)
  })
  it('positions landscape joints within the letterbox on a tall viewport', () => {
    const [geometry] = skeletonGeometry([pose()], 1920, 1080, 600, 1000)
    expect(geometry.points[0].x).toBeCloseTo(120)
    expect(geometry.points[0].y).toBeCloseTo(432.5)
  })
  it('skips missing, out-of-image, malformed and invisible joints without inventing connections', () => {
    const partial = pose()
    partial[11] = [NaN, .3, 1]
    partial[13] = [1.1, .4, 1]
    partial[15] = [.4, .5, .55]
    render(<Skeletons poses={[partial]} sourceWidth={300} sourceHeight={600} width={390} height={844} />)
    const svg = screen.getByTestId('camera-skeletons')
    expect(svg.querySelectorAll('circle')).toHaveLength(1)
    expect(svg.querySelectorAll('line')).toHaveLength(0)
    expect(skeletonGeometry([[]], 300, 600, 390, 844)).toEqual([])
    expect(skeletonGeometry([pose()], 0, 600, 390, 844)).toEqual([])
  })
  it('draws only supplied poses even when there are twenty tracked person boxes, and hides stale poses', () => {
    vi.stubGlobal('ResizeObserver', class {
      callback: ResizeObserverCallback
      constructor(callback: ResizeObserverCallback) { this.callback = callback }
      observe() { this.callback([{ contentRect: { width: 1000, height: 600 } } as ResizeObserverEntry], this as unknown as ResizeObserver) }
      disconnect() {}
    })
    const now = 10000
    const tracks = Array.from({ length: 20 }, (_, id) => ({ id, box: [.1, .2, .5, .8], observed: true, ambiguous: true }))
    const camera: WallCamera = { id: 'C1', label: 'CAM-01', name: 'Classroom', floorId: null, slot: null, sample: false, status: 'live', compute: 'device', analysis: 'current', image: 'blob:actual-frame', fps: 10, people: 20, generation: 'g1', preview: { width: 300, height: 600, timestampMs: 500, received: now, generation: 'g1' }, result: { backend: 'camera-device', timestampMs: 500, evidenceTimestampMs: 500, inferenceMs: 200, poses: [pose()], tracks, coverage: { observedPeople: 20, analyzedPeople: 1, actionPeople: 1, excludedPeople: 19, status: 'limited' } } }
    const view = render(<CameraTile camera={camera} events={[]} now={now} size="hero" />)
    expect(view.container.querySelectorAll('.cm-person-track')).toHaveLength(20)
    expect(screen.getByTestId('camera-skeletons').querySelectorAll('g[data-pose]')).toHaveLength(1)
    view.rerender(<CameraTile camera={camera} events={[]} now={now + 3000} size="hero" />)
    expect(screen.queryByTestId('camera-skeletons')).toBeNull()
    expect(view.container.querySelectorAll('.cm-person-track')).toHaveLength(0)
  })
})
