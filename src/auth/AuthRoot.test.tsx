import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuthRoot } from './AuthRoot'
import { useSession } from './context'
import { ApiError } from '../classroom/contracts'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../classroom/contracts', async importOriginal => ({ ...await importOriginal<typeof import('../classroom/contracts')>(), api }))
vi.mock('./session', () => ({ authMode: 'dev', clerkKey: '', setTokenProvider: vi.fn(), sessionToken: async () => null }))
vi.mock('@clerk/clerk-react', () => ({ ClerkProvider: ({ children }: { children: ReactNode }) => <>{children}</>, useAuth: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
function SessionButton() {
  const session = useSession()
  return <><p>{session.signedIn ? 'Signed in' : 'Signed out'}</p><button onClick={() => void session.signOut()}>Sign out</button></>
}
describe('owner workspace sign-out', () => {
  it.each([
    { userId: 'private-owner', workspace: { id: 'workspace-1', name: 'Workshop', ownerVerification: 'unverified' } },
    { userId: 'dev_legacy_operator' },
  ])('revokes the operator cookie session for $userId, then refreshes access', async principal => {
    api.mockResolvedValueOnce({ ...principal, role: 'admin', authMode: 'dev', name: 'Owner', email: null, guard: null }).mockResolvedValueOnce(undefined).mockRejectedValueOnce(new ApiError('Sign in required', 403))
    await act(async () => { render(<AuthRoot><SessionButton /></AuthRoot>) })
    expect(screen.getByText('Signed in')).toBeInTheDocument()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Sign out' })))
    expect(api).toHaveBeenCalledWith('/operator/logout', 'POST')
    expect(api).not.toHaveBeenCalledWith('/auth/dev/logout', 'POST')
    expect(screen.getByText('Signed out')).toBeInTheDocument()
  })
  it('preserves the local developer identity logout route', async () => {
    api.mockResolvedValueOnce({ userId: 'local-developer', role: 'admin', authMode: 'dev', name: 'Local admin', email: null, guard: null }).mockResolvedValueOnce(undefined).mockRejectedValueOnce(new ApiError('Sign in required', 403))
    await act(async () => { render(<AuthRoot><SessionButton /></AuthRoot>) })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Sign out' })))
    expect(api).toHaveBeenCalledWith('/auth/dev/logout', 'POST')
    expect(api).not.toHaveBeenCalledWith('/operator/logout', 'POST')
    expect(screen.getByText('Signed out')).toBeInTheDocument()
  })
})
