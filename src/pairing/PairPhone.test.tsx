import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PairPhone from './PairPhone'
import { tokenForPhone } from './pairingToken'
const { api, scan } = vi.hoisted(() => ({ api: vi.fn(), scan: vi.fn() }))
vi.mock('../classroom/contracts', async original => ({ ...await original<typeof import('../classroom/contracts')>(), api }))
vi.mock('./qrScanner', () => ({ startQRScanner: scan }))
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
const token = 'abcdefghijklmnopqrstuv0123456789'
describe('connect a camera or guard phone', () => {
  it('accepts only same-origin device QR links for the exact chosen role', () => {
    const origin = 'https://nivra.tanishq.work'
    expect(tokenForPhone(`${origin}/camera#pair=${token}`, 'camera', origin)).toBe(token)
    for (const input of [`https://evil.example/camera#pair=${token}`, `/guard#pair=${token}`, `/wall#operator=${token}`, `/camera#pair=${token}&operator=${token}`, `/camera#pair=${token}&pair=${token}`, 'javascript:alert(1)']) expect(tokenForPhone(input, 'camera', origin)).toBeNull()
  })
  it('does not request camera access when opened or when Scan QR is merely selected', () => {
    render(<PairPhone kind="camera" onPaired={vi.fn()} />)
    expect(screen.getByRole('heading')).toHaveTextContent('Connect your camera phone')
    expect(scan).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Scan QR' }))
    expect(scan).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Start scanner' })).toBeEnabled()
  })
  it('normalizes the code, exchanges the scoped cookie, then announces success before continuing', async () => {
    vi.useFakeTimers(); api.mockResolvedValue({})
    const done = vi.fn()
    render(<PairPhone kind="guard" onPaired={done} />)
    fireEvent.click(screen.getByRole('button', { name: 'Enter code' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Pairing code' }), { target: { value: 'abcd-2345' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Connect phone' })))
    expect(api).toHaveBeenCalledExactlyOnceWith('/guard/pair', 'POST', { code: 'ABCD2345' })
    expect(screen.getByRole('status')).toHaveTextContent("You're connected.")
    expect(done).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(240))
    expect(done).toHaveBeenCalledOnce()
  })
  it('keeps an invalid or expired code editable for retry', async () => {
    api.mockRejectedValueOnce(new Error('Code expired. Ask for a new one.'))
    render(<PairPhone kind="camera" onPaired={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Enter code' }))
    const input = screen.getByRole('textbox', { name: 'Pairing code' })
    fireEvent.change(input, { target: { value: 'ABCD2345' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Connect phone' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Code expired')
    expect(input).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Connect phone' })).toBeEnabled()
  })
  it('rejects the wrong role without navigation and aborts scanning on cancel or unmount', async () => {
    let decoded!: (value: string) => void
    let signal!: AbortSignal
    scan.mockImplementation(async (_video, callback, nextSignal) => { decoded = callback; signal = nextSignal; return { stop: vi.fn() } })
    const view = render(<PairPhone kind="camera" onPaired={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Scan QR' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start scanner' })))
    act(() => decoded(`${location.origin}/guard#pair=${token}`))
    expect(screen.getByRole('alert')).toHaveTextContent('Use the camera QR')
    expect(api).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel scanner' }))
    expect(signal.aborted).toBe(true)
    act(() => decoded(`${location.origin}/camera#pair=${token}`))
    expect(api).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Scan QR' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start scanner' })))
    view.unmount()
    expect(signal.aborted).toBe(true)
  })
  it('stops the scanner before redeeming a valid QR and ignores duplicate decoded frames', async () => {
    let decoded!: (value: string) => void
    let signal!: AbortSignal
    scan.mockImplementation(async (_video, callback, nextSignal) => { decoded = callback; signal = nextSignal })
    api.mockReturnValue(new Promise(() => {}))
    render(<PairPhone kind="camera" onPaired={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Scan QR' }))
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Start scanner' })))
    act(() => { decoded(`${location.origin}/camera#pair=${token}`); decoded(`${location.origin}/camera#pair=${token}`) })
    expect(signal.aborted).toBe(true)
    expect(api).toHaveBeenCalledExactlyOnceWith('/camera/pair', 'POST', { token })
  })
})
