import type { ReactNode } from 'react'
import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('./classroom/contracts', () => ({ api, isLocalDashboard: false }))
vi.mock('./auth/AuthRoot', () => ({ AuthRoot: ({ children }: { children: ReactNode }) => <>{children}</> }))
vi.mock('./auth/context', () => ({ useSession: () => ({ mode: 'dev', ready: true, signedIn: false, me: null }) }))
vi.mock('./auth/RequireRole', () => ({ RequireRole: () => <p>Developer role picker</p> }))
vi.mock('./auth/LoginPage', () => ({ AccessMessage: ({ title, children }: { title: string; children: ReactNode }) => <main><h1>{title}</h1>{children}</main> }))
vi.mock('./pairing/PairPhone', () => ({ default: ({ kind }: { kind: string }) => <h1>Connect your {kind} phone</h1> }))
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllEnvs(); history.replaceState(null, '', '/') })

describe('public pilot access', () => {
  it('offers direct site setup instead of an owner verification gate', async () => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
    const { default: App } = await import('./App')
    history.replaceState(null, '', '/wall')
    await act(async () => { render(<App />) })
    expect(screen.getByText('Set up your site')).toBeInTheDocument()
    expect(screen.queryByText('Developer role picker')).not.toBeInTheDocument()
  })
  it('asks an unpaired public guard phone for its assigned QR', async () => {
    vi.stubEnv('VITE_NIVRA_DIRECT_SOCKET_RELAY', '1')
    const { default: App } = await import('./App')
    api.mockRejectedValueOnce(new Error('Pair first'))
    history.replaceState(null, '', '/guard')
    await act(async () => { render(<App />) })
    expect(await screen.findByText('Connect your guard phone')).toBeInTheDocument()
    expect(screen.queryByText('Developer role picker')).not.toBeInTheDocument()
  })
})
