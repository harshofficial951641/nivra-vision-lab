import { StrictMode, type ReactNode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const { api, authMounted } = vi.hoisted(() => ({ api: vi.fn(), authMounted: vi.fn() }))
vi.mock('./classroom/contracts', () => ({ api, isLocalDashboard: true }))
vi.mock('./auth/AuthRoot', () => ({ AuthRoot: ({ children }: { children: ReactNode }) => { authMounted(); return <>{children}</> } }))
vi.mock('./auth/LoginPage', () => ({ AccessMessage: ({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) => <main><h1>{title}</h1>{children}{action}</main>, LoginPage: () => <p>Developer role picker</p> }))
vi.mock('./mobile/WorkspaceStart', () => ({ default: () => <h1>Create private site</h1> }))
vi.mock('./mobile/MobileHome', () => ({ default: () => <h1>Choose your workspace</h1> }))
vi.mock('./mobile/OwnerAccess', () => ({ default: () => <h1>Open your private console.</h1> }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); history.replaceState(null, '', '/') })

describe('release entry routes', () => {
  it('redeems an owner invite once before mounting authentication, strips the hash, then opens guided setup', async () => {
    const token = 'owner-once-01234567890123456789012345'
    let finish!: (value: unknown) => void
    api.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const replace = vi.fn()
    history.replaceState(null, '', `/#operator=${token}`)
    vi.stubGlobal('location', { pathname: '/', search: '', hash: `#operator=${token}`, replace })
    render(<StrictMode><App /></StrictMode>)
    expect(api).toHaveBeenCalledExactlyOnceWith('/operator/redeem', 'POST', { token })
    expect(window.history.state).toBeNull()
    expect(authMounted).not.toHaveBeenCalled()
    await act(async () => { finish({}) })
    expect(replace).toHaveBeenCalledExactlyOnceWith('/setup?onboarding=1')
    expect(authMounted).not.toHaveBeenCalled()
  })
  it('keeps a failed invite outside authentication and explains the failure', async () => {
    history.replaceState(null, '', '/#operator=expired-owner-012345678901234567890')
    api.mockRejectedValueOnce(new Error('Owner link expired.'))
    await act(async () => { render(<App />) })
    expect(screen.getByRole('alert')).toHaveTextContent('Owner link expired.')
    expect(location.hash).toBe('')
    expect(authMounted).not.toHaveBeenCalled()
  })
  it.each(['/', '/mobile'])('opens the role launcher at %s without a login or camera exchange', async route => {
    history.replaceState(null, '', route)
    await act(async () => { render(<App />) })
    expect(await screen.findByText(route === '/' ? 'Create private site' : 'Choose your workspace')).toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
    expect(authMounted).not.toHaveBeenCalled()
  })
  it('routes the local owner page without mounting authentication or automatically minting a QR', async () => {
    history.replaceState(null, '', '/owner')
    await act(async () => { render(<App />) })
    expect(await screen.findByRole('heading', { name: 'Open your private console.' })).toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
    expect(authMounted).not.toHaveBeenCalled()
  })

})
