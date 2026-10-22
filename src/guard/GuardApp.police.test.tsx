import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GuardApp from './GuardApp'
import type { GuardAlert } from './useGuard'

const { state } = vi.hoisted(() => ({ state: { alerts: [] as GuardAlert[] } }))
vi.mock('../auth/context', () => ({ useOptionalSession: () => null }))
vi.mock('./useGuard', () => ({ enablePush: vi.fn(), useGuard: () => ({ view: { callsign: 'G2', name: 'Asha', floorName: 'Floor 2', shift: 'on_shift', gps: null, floor: null, post: null }, alerts: state.alerts, connection: 'connected', problem: '', act: vi.fn(), setShift: vi.fn(), saveGPS: vi.fn(), saveFloor: vi.fn() }) }))
vi.mock('../location/useLiveGPS', () => ({ useLiveGPS: () => ({ point: null, error: '', age: 0, retry: vi.fn() }) }))
vi.mock('../location/GoogleMap', () => ({ GoogleMap: () => <div>Location</div> }))
vi.mock('./ringPlayer', () => ({ RING_MS: 4000, shouldRing: () => false, RingPlayer: class { prime = async () => true; stop = vi.fn(); dispose = vi.fn() } }))

beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); state.alerts = [] })
describe('guard police integration', () => {
  it.each([false, true])('shows the control and latest contact on incoming/responding screen (%s)', async responding => {
    vi.useFakeTimers()
    state.alerts = [{ id: 'e1', camera_id: 'c1', camera_name: 'Entrance', location: 'Floor 2', detail: 'Motion', received_at: 1000, alerted_at: 1100, guard_ack_at: responding ? 1200 : null, status: 'acknowledged', revision: 2, police: { at: new Date(2026, 9, 23, 14, 32).getTime(), by: 'guard:G2', method: 'call', count: 1 } }]
    render(<GuardApp />)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start shift' })))
    expect(screen.getByRole('heading', { name: 'Go to Entrance' })).toBeVisible()
    expect(screen.getByText('Police contacted (call) by G2 at 14:32')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    act(() => vi.advanceTimersByTime(3000))
    expect(screen.getAllByRole('group', { name: 'Contact police' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Police' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('link', { name: 'Call 112' })).toHaveAttribute('href', 'tel:112')
    expect(screen.getByRole('link', { name: 'Text police' }).getAttribute('href')).toContain(encodeURIComponent('Entrance, Floor 2'))
  })
})
