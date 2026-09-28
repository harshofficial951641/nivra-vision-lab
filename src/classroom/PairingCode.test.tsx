import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PairingCode } from './PairingCode'
afterEach(() => { cleanup(); vi.useRealTimers() })
describe('Phone pairing code', () => {
  it('only exposes a scannable code while a remote invitation is valid', () => {
    vi.useFakeTimers()
    const renew = vi.fn()
    render(<PairingCode url="https://example.com/camera#pair=test" expiresAt={Date.now()+1000} remoteReady renew={renew} />)
    expect(screen.getByTitle('Scan with your phone camera to connect this classroom')).toBeTruthy()
    act(() => vi.advanceTimersByTime(2000))
    expect(screen.queryByTitle('Scan with your phone camera to connect this classroom')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Generate a new code' }))
    expect(renew).toHaveBeenCalledOnce()
  })
  it('does not offer a localhost QR to phones', () => {
    render(<PairingCode url="http://127.0.0.1:8765/camera#pair=test" expiresAt={Date.now()+300000} remoteReady={false} renew={() => {}} />)
    expect(screen.queryByTitle('Scan with your phone camera to connect this classroom')).toBeNull()
    expect(screen.getByText(/public bridge is connected/)).toBeTruthy()
  })
})
