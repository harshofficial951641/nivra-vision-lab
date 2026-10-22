import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GuardApp from './GuardApp'
const { setShift, tracking, view } = vi.hoisted(() => ({ setShift: vi.fn(), tracking: vi.fn(), view: { callsign: 'G1', name: 'Asha', floorName: 'Floor 2', shift: 'break', gps: null, floor: null, post: null } }))
vi.mock('../auth/context', () => ({ useOptionalSession: () => null }))
vi.mock('./useGuard', () => ({ enablePush: vi.fn(), useGuard: () => ({ view, alerts: [], connection: 'connected', problem: '', act: vi.fn(), setShift, saveGPS: vi.fn(), saveFloor: vi.fn() }) }))
vi.mock('../location/useLiveGPS', () => ({ useLiveGPS: (enabled: boolean) => { tracking(enabled); return { point: null, error: '', age: 0, retry: vi.fn() } } }))
vi.mock('./ringPlayer', () => ({ RING_MS: 4000, shouldRing: () => false, RingPlayer: class { prime = async () => true; stop = vi.fn(); dispose = vi.fn() } }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.restoreAllMocks(); view.shift = 'break' })

describe('guard phone onboarding', () => {
  it('resumes an existing break before starting GPS and alert readiness', async () => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    setShift.mockImplementationOnce(async () => { view.shift = 'on_shift' })
    render(<GuardApp />)
    expect(screen.getByRole('region', { name: 'Guard phone setup' })).toHaveTextContent('Start your shift to receive alerts.')
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start shift' })))
    expect(setShift).toHaveBeenCalledExactlyOnceWith('on_shift')
    expect(screen.getByRole('radio', { name: 'On shift' })).toHaveAttribute('aria-checked', 'true')
    expect(tracking).toHaveBeenLastCalledWith(true)
  })
  it('keeps the start screen available and GPS paused if saving the shift fails', async () => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    setShift.mockRejectedValueOnce(new Error('Shift could not be saved.'))
    render(<GuardApp />)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start shift' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Shift could not be saved.')
    expect(screen.getByRole('button', { name: 'Start shift' })).toBeEnabled()
    expect(tracking).toHaveBeenLastCalledWith(false)
  })
  it('keeps the saved floor visible while edits and native alert tools are optional', async () => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('NIVRA-Native iOS/1.0')
    setShift.mockImplementationOnce(async () => { view.shift = 'on_shift' })
    render(<GuardApp />)
    expect(screen.getByText('Asha · G1 · Floor 2')).toBeVisible()
    const floor = screen.getByLabelText('Current floor')
    expect(floor).toBeRequired()
    expect(floor.closest('details')).not.toHaveAttribute('open')
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start shift' })))
    expect(screen.getByRole('button', { name: 'Test ring' }).closest('details')).not.toHaveAttribute('open')
    expect(screen.queryByRole('button', { name: 'Alerts when locked' })).not.toBeInTheDocument()
    expect(screen.getByText('Keep this screen open to hear alerts. Lock-screen alerts are unavailable in this app.')).toBeInTheDocument()
  })

})
