import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import WorkspaceStart from './WorkspaceStart'
import { ApiError } from '../classroom/contracts'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../classroom/contracts', async importOriginal => ({ ...await importOriginal<typeof import('../classroom/contracts')>(), api }))
afterEach(() => { cleanup(); api.mockReset(); vi.unstubAllGlobals() })
const setup = () => { const replace = vi.fn(); vi.stubGlobal('location', { replace }); render(<StrictMode><WorkspaceStart /></StrictMode>); return replace }

describe('website-first private workspace entry', () => {
  it('starts with one click and no required name, owner verification or local bootstrap', async () => {
    api.mockRejectedValueOnce(new ApiError('Sign in required', 403)).mockResolvedValueOnce({ workspace: { id: 'private-1', name: 'My place', ownerVerification: 'unverified' } })
    const replace = setup()
    await act(async () => {})
    expect(screen.getByText('Name your place (optional)').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByLabelText('Place name')).not.toBeRequired()
    expect(api).toHaveBeenCalledExactlyOnceWith('/me')
    expect(screen.queryByRole('link', { name: /owner access|owner QR|verify owner/i })).not.toBeInTheDocument()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Get started' })))
    expect(api).toHaveBeenCalledWith('/workspaces', 'POST', { name: 'My place' })
    expect(replace).toHaveBeenCalledExactlyOnceWith('/setup?onboarding=1#cameras')
    expect(api.mock.calls.some(([path]) => ['/session', '/operator/invite', '/auth/dev'].includes(path))).toBe(false)
  })
  it('resumes an existing admin workspace without creating another workspace', async () => {
    api.mockResolvedValueOnce({ role: 'admin', workspace: { id: 'existing', name: 'Existing site', ownerVerification: 'unverified' } })
    const replace = setup()
    await act(async () => {})
    expect(replace).toHaveBeenCalledExactlyOnceWith('/wall')
    expect(api).toHaveBeenCalledExactlyOnceWith('/me')
  })
  it('keeps the typed site name after creation fails and permits a retry', async () => {
    api.mockRejectedValueOnce(new ApiError('Sign in required', 403)).mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce({ workspace: { id: 'one', name: 'Workshop', ownerVerification: 'unverified' } })
    const replace = setup()
    await act(async () => {})
    fireEvent.click(screen.getByText('Name your place (optional)'))
    fireEvent.change(screen.getByLabelText('Place name'), { target: { value: 'Workshop' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Get started' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Connection interrupted')
    expect(screen.getByLabelText('Place name')).toHaveValue('Workshop')
    expect(replace).not.toHaveBeenCalled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Get started' })))
    expect(replace).toHaveBeenCalledExactlyOnceWith('/setup?onboarding=1#cameras')
  })
  it('does not upgrade an existing guard role or create any site on page load', async () => {
    api.mockResolvedValueOnce({ role: 'guard', name: 'Asha', guard: { callsign: 'G1' } })
    const replace = setup()
    await act(async () => {})
    expect(screen.getByRole('link', { name: 'Open guard screen' })).toHaveAttribute('href', '/guard')
    expect(screen.queryByRole('button', { name: 'Get started' })).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
    expect(api).toHaveBeenCalledExactlyOnceWith('/me')
  })
  it('does not treat a service failure as a fresh workspace and retries the session check', async () => {
    api.mockRejectedValueOnce(new Error('Service offline')).mockRejectedValueOnce(new ApiError('No session', 403))
    setup()
    await act(async () => {})
    expect(screen.getByRole('button', { name: 'Get started' })).toBeDisabled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Retry connection' })))
    expect(screen.getByRole('button', { name: 'Get started' })).toBeEnabled()
    expect(api.mock.calls.every(([path]) => path === '/me')).toBe(true)
  })
  it('does not create two places while the first click is still saving', async () => {
    api.mockRejectedValueOnce(new ApiError('Sign in required', 403)).mockReturnValueOnce(new Promise(() => {}))
    setup()
    await act(async () => {})
    const start = screen.getByRole('button', { name: 'Get started' })
    fireEvent.click(start)
    fireEvent.click(start)
    expect(api.mock.calls.filter(([path]) => path === '/workspaces')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Getting ready…' })).toBeDisabled()
  })
})
