import { useState } from 'react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CameraFocus } from './CommandWall'
import type { WallCamera } from './model'

const cameras: WallCamera[] = ['Entrance', 'Hall', 'Garden'].map((name, index) => ({ id: String(index), label: `CAM-${index + 1}`, name, floorId: null, slot: null, status: 'offline', sample: false, image: '', fps: null, people: null }))
const showModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const close = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false } })
})
afterAll(() => {
  if (showModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', showModal)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (close) Object.defineProperty(HTMLDialogElement.prototype, 'close', close)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
afterEach(cleanup)
const map = vi.fn(), pin = vi.fn(), dismiss = vi.fn()
function Focus({ list = cameras }: { list?: WallCamera[] }) {
  const [id, setId] = useState('0')
  return <CameraFocus cameras={list} cameraId={id} change={setId} events={[]} now={1000} pinned={[]} openMap={map} togglePin={pin} close={dismiss} />
}
const swipe = (dx: number, dy = 0) => {
  const frame = screen.getByRole('group', { name: 'Camera footage' })
  fireEvent.touchStart(frame, { touches: [{ clientX: 200, clientY: 200 }] })
  fireEvent.touchEnd(frame, { changedTouches: [{ clientX: 200 + dx, clientY: 200 + dy }] })
}

describe('focused camera navigation', () => {
  it('supports visible buttons, arrow keys, and left/right swipes without triggering other actions', () => {
    map.mockClear(); pin.mockClear(); dismiss.mockClear()
    render(<Focus />)
    expect(screen.getByRole('dialog', { name: 'Entrance' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Next camera' }))
    expect(screen.getByRole('dialog', { name: 'Hall' })).toBeVisible()
    swipe(-100)
    expect(screen.getByRole('dialog', { name: 'Garden' })).toBeVisible()
    swipe(100)
    expect(screen.getByRole('dialog', { name: 'Hall' })).toBeVisible()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowLeft' })
    expect(screen.getByRole('dialog', { name: 'Entrance' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Previous camera' }))
    expect(screen.getByRole('dialog', { name: 'Garden' })).toBeVisible()
    expect(map).not.toHaveBeenCalled(); expect(pin).not.toHaveBeenCalled(); expect(dismiss).not.toHaveBeenCalled()
  })
  it('ignores taps, vertical scrolling, short gestures, cancelled gestures and two-finger zoom', () => {
    render(<Focus />)
    swipe(20); swipe(-90, 140)
    const frame = screen.getByRole('group', { name: 'Camera footage' })
    fireEvent.touchStart(frame, { touches: [{ clientX: 200, clientY: 200 }] })
    fireEvent.touchCancel(frame)
    fireEvent.touchEnd(frame, { changedTouches: [{ clientX: 20, clientY: 200 }] })
    fireEvent.touchStart(frame, { touches: [{ clientX: 200, clientY: 200 }, { clientX: 210, clientY: 200 }] })
    fireEvent.touchEnd(frame, { changedTouches: [{ clientX: 20, clientY: 200 }] })
    expect(screen.getByRole('dialog', { name: 'Entrance' })).toBeVisible()
  })
  it('keeps single-camera navigation inert and only opens map through an explicit click', () => {
    map.mockClear()
    render(<Focus list={cameras.slice(0, 1)} />)
    expect(screen.getByRole('button', { name: 'Next camera' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Previous camera' })).toBeDisabled()
    swipe(-120)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'ArrowRight' })
    expect(screen.getByRole('dialog', { name: 'Entrance' })).toBeVisible()
    expect(map).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Map' }))
    expect(map).toHaveBeenCalledExactlyOnceWith('0')
  })
})
