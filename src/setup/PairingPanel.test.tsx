import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PairingPanel } from './PairingPanel'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../classroom/contracts', () => ({ api }))
vi.mock('../auth/context', () => ({ useSession: () => ({ mode: 'dev' }) }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.useRealTimers(); Reflect.deleteProperty(navigator, 'clipboard') })

describe('private phone pairing', () => {
  it('shows a clear QR once and keeps the raw capability inside a closed disclosure', async () => {
    const url='https://nivra.tanishq.work/camera#pair=private-test-capability'
    api.mockResolvedValue({ url, expiresInSeconds:300, remoteReady:true })
    const close=vi.fn()
    await act(async () => render(<StrictMode><PairingPanel endpoint="/cameras/c1/pair" label="Entrance" kind="camera" onClose={close} fail={vi.fn()} /></StrictMode>))
    expect(api).toHaveBeenCalledTimes(1)
    expect(screen.getByTitle('Pairing code for Entrance')).toBeInTheDocument()
    expect(screen.getByText(url).closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText(/Tap Allow camera & start/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name:'Close' }))
    expect(close).toHaveBeenCalledTimes(1)
    expect(api).toHaveBeenCalledTimes(1)
  })

  it('creates a replacement only when an expired-code button is pressed', async () => {
    api.mockResolvedValueOnce({ url:'https://nivra.tanishq.work/guard#pair=expired', expiresInSeconds:0, remoteReady:true })
      .mockResolvedValueOnce({ url:'https://nivra.tanishq.work/guard#pair=refreshed', expiresInSeconds:300, remoteReady:true })
    await act(async () => render(<PairingPanel endpoint="/guards/G1/pair" label="Asha" kind="guard" onClose={vi.fn()} fail={vi.fn()} />))
    expect(api).toHaveBeenCalledTimes(1)
    await act(async () => fireEvent.click(screen.getByRole('button', { name:'New code' })))
    expect(api).toHaveBeenCalledTimes(2)
    expect(screen.getByTitle('Pairing code for Asha')).toBeInTheDocument()
  })

  it('formats and copies the short code, with feedback that clears after a moment', async () => {
    vi.useFakeTimers()
    const writeText=vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true})
    api.mockResolvedValue({url:'https://nivra.tanishq.work/camera#pair=private',pairingCode:'ab12cd34',expiresInSeconds:300,remoteReady:true})
    await act(async () => render(<PairingPanel endpoint="/cameras/c1/pair" label="Entrance" kind="camera" onClose={vi.fn()} fail={vi.fn()} />))
    expect(screen.getByText('AB12 CD34')).not.toBeVisible()
    fireEvent.click(screen.getByText('Use a code instead',{selector:'summary'}))
    expect(screen.getByText('AB12 CD34')).toBeVisible()
    await act(async () => fireEvent.click(screen.getByRole('button',{name:'Copy code'})))
    expect(writeText).toHaveBeenCalledWith('AB12CD34')
    expect(screen.getByRole('button',{name:'Copied'})).toBeVisible()
    expect(screen.getByText('https://nivra.tanishq.work/camera#pair=private')).not.toBeVisible()
    await act(async () => { vi.advanceTimersByTime(2300) })
    expect(screen.getByRole('button',{name:'Copy code'})).toBeVisible()
  })

  it('replaces the QR with a connected state without creating another invitation', async () => {
    api.mockResolvedValue({url:'https://nivra.tanishq.work/camera#pair=private',pairingCode:'AB12CD34',expiresInSeconds:300,remoteReady:true})
    const close=vi.fn()
    const view=render(<PairingPanel endpoint="/cameras/c1/pair" label="Entrance" kind="camera" onClose={close} fail={vi.fn()} />)
    await act(async () => {})
    view.rerender(<PairingPanel endpoint="/cameras/c1/pair" label="Entrance" kind="camera" connected onClose={close} fail={vi.fn()} />)
    expect(screen.getByText('Phone connected')).toBeVisible()
    expect(screen.queryByTitle('Pairing code for Entrance')).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'New code'})).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Done'}))
    expect(close).toHaveBeenCalledTimes(1)
    expect(api).toHaveBeenCalledTimes(1)
  })

  it('does not revoke an already-connected phone just by opening the panel', () => {
    render(<StrictMode><PairingPanel endpoint="/guards/G1/pair" label="Asha" kind="guard" connected onClose={vi.fn()} fail={vi.fn()} /></StrictMode>)
    expect(screen.getByText('Phone connected')).toBeVisible()
    expect(api).not.toHaveBeenCalled()
  })
  it('preserves a linked phone and waits for actual live video without minting a replacement', () => {
    const props={endpoint:'/cameras/c1/pair',label:'Entrance',kind:'camera' as const,onClose:vi.fn(),fail:vi.fn()}
    const view=render(<StrictMode><PairingPanel {...props} paired /></StrictMode>)
    expect(screen.getByText('Phone linked')).toBeVisible()
    expect(screen.getByText(/On that phone, tap Allow camera/)).toBeVisible()
    expect(screen.queryByTitle('Pairing code for Entrance')).not.toBeInTheDocument()
    expect(screen.queryByRole('button',{name:'New code'})).not.toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
    view.rerender(<PairingPanel {...props} paired connected />)
    expect(screen.getByText('Your camera is live. You can watch it now.')).toBeVisible()
    expect(api).not.toHaveBeenCalled()
  })

  it('hides a consumed QR as soon as pairing succeeds, before video starts', async () => {
    api.mockResolvedValue({url:'https://nivra.tanishq.work/camera#pair=private',expiresInSeconds:300,remoteReady:true})
    const props={endpoint:'/cameras/c1/pair',label:'Entrance',kind:'camera' as const,onClose:vi.fn(),fail:vi.fn()}
    const view=render(<PairingPanel {...props} />)
    await act(async()=>{})
    expect(screen.getByTitle('Pairing code for Entrance').closest('svg')).toBeVisible()
    view.rerender(<PairingPanel {...props} paired />)
    expect(screen.queryByTitle('Pairing code for Entrance')).not.toBeInTheDocument()
    expect(screen.getByText('Phone linked')).toBeVisible()
    expect(api).toHaveBeenCalledTimes(1)
  })

  it('replaces a linked phone only after an explicit confirmed change', async () => {
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    api.mockResolvedValue({url:'https://nivra.tanishq.work/camera#pair=replacement',expiresInSeconds:300,remoteReady:true})
    render(<PairingPanel endpoint="/cameras/c1/pair" label="Entrance" kind="camera" paired onClose={vi.fn()} fail={vi.fn()} />)
    fireEvent.click(screen.getByRole('button',{name:'Change phone'}))
    expect(api).not.toHaveBeenCalled()
    confirm.mockReturnValue(true)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Change phone'})))
    expect(api).toHaveBeenCalledExactlyOnceWith('/cameras/c1/pair','POST')
    expect(screen.getByTitle('Pairing code for Entrance').closest('svg')).toBeVisible()
    confirm.mockRestore()
  })

})
