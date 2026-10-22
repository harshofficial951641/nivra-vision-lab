import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MobileHome from './MobileHome'
import { pairingDestination } from './pairingDestination'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('simple phone launcher', () => {
  it('lets keyboard users choose a role and keeps inactive links out of the tab order', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false })))
    render(<MobileHome />)
    const scrollTo = vi.fn()
    Object.defineProperty(screen.getByRole('tabpanel', { name: 'Camera' }).parentElement!, 'scrollTo', { value: scrollTo })
    const camera = screen.getByRole('tab', { name: 'Camera' })
    fireEvent.keyDown(camera, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Guard' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('link', { name: 'Open guard' })).toHaveAttribute('tabindex', '0')
    expect(screen.queryByRole('link', { name: 'Open camera' })).not.toBeInTheDocument()
    expect(scrollTo).toHaveBeenCalled()
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Guard' }), { key: 'End' })
    expect(screen.getByRole('link', { name: 'Watch cameras' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Next role' })).toBeDisabled()
  })
  it('updates the visible role after a native swipe without navigating or activating the role', () => {
    render(<MobileHome />)
    const deck = screen.getByRole('tabpanel', { name: 'Camera' }).parentElement!
    Object.defineProperty(deck, 'clientWidth', { configurable: true, value: 390 })
    fireEvent.scroll(deck, { target: { scrollLeft: 390 } })
    expect(screen.getByRole('tab', { name: 'Guard' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('link', { name: 'Open guard' })).toHaveAttribute('href', '/guard')
    expect(screen.queryByRole('link', { name: 'Open camera' })).not.toBeInTheDocument()
  })
  it('accepts only same-site links for their assigned camera, guard or owner role', () => {
    const token = 'abcdefghijklmnopqrstuv0123456789'
    expect(pairingDestination(`/camera#pair=${token}`, 'https://nivra.tanishq.work')).toBe(`/camera#pair=${token}`)
    expect(pairingDestination(`https://other.example/guard#pair=${token}`, 'https://nivra.tanishq.work')).toBeNull()
    expect(pairingDestination(`/wall#pair=${token}`, 'https://nivra.tanishq.work')).toBeNull()
    expect(pairingDestination(`/guard#operator=${token}`, 'https://nivra.tanishq.work')).toBeNull()
    expect(pairingDestination('javascript:alert(1)', 'https://nivra.tanishq.work')).toBeNull()
  })
})
