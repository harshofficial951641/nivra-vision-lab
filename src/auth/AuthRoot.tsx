import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ClerkProvider, useAuth } from '@clerk/clerk-react'
import { ApiError, api } from '../classroom/contracts'
import { AuthContext, type AuthState } from './context'
import { authMode, clerkKey, setTokenProvider, type Me, type Role } from './session'

function useMe(enabled: boolean) {
  const [me, setMe] = useState<Me | null>(null)
  const [problem, setProblem] = useState('')
  const [checked, setChecked] = useState(false)
  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>('/me'))
      setProblem('')
    } catch (reason) {
      setMe(null)
      const status = reason instanceof ApiError ? reason.status : 0
      setProblem(
        status === 401
          ? ''
          : status === 403
            ? 'no-role'
            : 'The NIVRA service is not reachable. Check that it is running on the showcase laptop.',
      )
    } finally {
      setChecked(true)
    }
  }, [])
  useEffect(() => {
    if (!enabled) {
      setMe(null)
      setProblem('')
      setChecked(true)
      return
    }
    setChecked(false)
    void refresh()
  }, [enabled, refresh])
  return { me, problem, checked, refresh }
}

function ClerkBridge({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth()
  // Install before the /me request below so it carries a token.
  setTokenProvider(() => getToken())
  const signedIn = Boolean(isLoaded && isSignedIn)
  const { me, problem, checked, refresh } = useMe(signedIn)
  const value = useMemo<AuthState>(
    () => ({
      mode: 'clerk',
      ready: isLoaded && checked,
      signedIn,
      me,
      problem,
      refresh,
      signOut: async () => {
        await signOut()
      },
      devSignIn: async () => {
        throw new Error('Developer sign-in is off because Clerk is configured.')
      },
    }),
    [isLoaded, checked, signedIn, me, problem, refresh, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

function DevBridge({ children }: { children: ReactNode }) {
  setTokenProvider(async () => null)
  const { me, problem, checked, refresh } = useMe(true)
  const value = useMemo<AuthState>(
    () => ({
      mode: 'dev',
      ready: checked,
      signedIn: Boolean(me),
      me,
      problem: problem === 'no-role' ? '' : problem,
      refresh,
      signOut: async () => {
        await api('/auth/dev/logout', 'POST').catch(() => undefined)
        await refresh()
      },
      devSignIn: async (role: Role, name: string, callsign?: string) => {
        // Dev guards are selected by call sign through the name field (contract §1).
        await api('/auth/dev', 'POST', { role, name: role === 'guard' && callsign ? callsign : name })
        await refresh()
      },
    }),
    [checked, me, problem, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function AuthRoot({ children }: { children: ReactNode }) {
  if (authMode === 'clerk')
    return (
      <ClerkProvider publishableKey={clerkKey} afterSignOutUrl={location.pathname.startsWith('/guard') ? '/guard' : '/login'}>
        <ClerkBridge>{children}</ClerkBridge>
      </ClerkProvider>
    )
  return <DevBridge>{children}</DevBridge>
}
