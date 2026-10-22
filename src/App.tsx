import { lazy, Suspense, useEffect, useState } from 'react'
import AccessGate from './classroom/AccessGate'
import { AuthRoot } from './auth/AuthRoot'
import { RequireRole } from './auth/RequireRole'
import { AccessMessage } from './auth/LoginPage'
import type { Role } from './auth/session'
import type { ReactNode } from 'react'
import { api } from './classroom/contracts'
import { useSession } from './auth/context'
import { Brand } from './ui/Brand'
const VisionLab = lazy(() => import('./VisionLab'))
const Dashboard = lazy(() => import('./classroom/Dashboard'))
const Publisher = lazy(() => import('./classroom/Publisher'))
const FightDemo = lazy(() => import('./FightDemo'))
const CommandWall = lazy(() => import('./command/CommandWall'))
const GuardApp = lazy(() => import('./guard/GuardApp'))
const SetupPortal = lazy(() => import('./setup/SetupPortal'))
const OwnerAccess = lazy(() => import('./mobile/OwnerAccess'))
const MobileHome = lazy(() => import('./mobile/MobileHome'))
const WorkspaceStart = lazy(() => import('./mobile/WorkspaceStart'))
const PairPhone = lazy(() => import('./pairing/PairPhone'))
const UsbSetup = lazy(() => import('./usb/UsbSetup'))
const publicRelay = import.meta.env.VITE_NIVRA_DIRECT_SOCKET_RELAY === '1'

function OwnerGuidance({ guard = false }: { guard?: boolean }) {
  return <AccessMessage dark title={guard ? 'Pair your guard phone' : 'Set up your site'} action={<a className="au-submit" href={guard ? '/mobile' : '/'}>{guard ? 'Choose a workspace' : 'Start setup'}</a>}>
    {guard ? 'Ask your owner for your guard QR. Scan it with this phone’s camera to get started.' : 'Name your place, then connect your phones. We’ll guide you through it.'}
  </AccessMessage>
}

function ReleaseRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const session = useSession()
  if (publicRelay && session.mode === 'dev' && session.ready && !session.signedIn) return <OwnerGuidance />
  return <RequireRole roles={roles} variant="reviewer">{children}</RequireRole>
}

let ownerExchange: { token: string; request: Promise<unknown> } | null = null
function OwnerInvitation({ token }: { token: string }) {
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    history.replaceState(null, '', location.pathname + location.search)
    if (!ownerExchange || ownerExchange.token !== token) {
      ownerExchange = { token, request: /^[A-Za-z0-9_-]{30,100}$/.test(token)
        ? api('/operator/redeem', 'POST', { token })
        : Promise.reject(new Error('This owner link is invalid. Ask for a new link.')) }
    }
    void ownerExchange.request.then(() => { if (active) location.replace('/setup?onboarding=1') }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'Could not open this owner link.')
    })
    return () => { active = false }
  }, [token])
  return <AccessMessage dark title={error ? 'Owner link unavailable' : 'Opening owner setup'} action={error ? <a className="au-submit" href="/mobile">Choose a workspace</a> : undefined}>
    <p role={error ? 'alert' : 'status'}>{error || 'Signing this browser in with your private owner link…'}</p>
  </AccessMessage>
}

/** A scoped QR session grants only this guard phone access, never operator access. */
function GuardAccess() {
  const { mode } = useSession()
  const [pairToken] = useState(() => new URLSearchParams(location.hash.slice(1)).get('pair'))
  const [prepared, setPrepared] = useState(false)
  const [pairError, setPairError] = useState('')
  const [paired, setPaired] = useState<boolean | null>(() => new URLSearchParams(location.hash.slice(1)).has('pair') ? true : null)
  useEffect(() => {
    if (mode !== 'clerk' || !pairToken || prepared) return
    try {
      // Clerk uses the hash for its own sign-in screens. Keep this short-lived
      // token on this tab until the assigned guard has authenticated.
      sessionStorage.setItem('nivra.guard.pendingPair', JSON.stringify({ token: pairToken, expiresAt: Date.now() + 300000 }))
      history.replaceState(null, '', location.pathname + location.search)
      setPrepared(true)
    } catch {
      setPairError('Sign in first, then scan the guard QR again. This browser could not retain the pairing code during sign-in.')
    }
  }, [mode, pairToken, prepared])
  useEffect(() => {
    if (mode !== 'dev' || paired !== null) return
    let active = true
    void api('/guard/session').then(() => { if (active) setPaired(true) }, () => { if (active) setPaired(false) })
    return () => { active = false }
  }, [mode, paired])
  if (pairError) return <p role="alert">{pairError} <a href="/guard">Open guard sign-in</a></p>
  if (mode === 'clerk' && pairToken && !prepared) return <p role="status">Preparing guard sign-in…</p>
  if (mode === 'dev' && paired === null) return <p role="status">Checking guard phone…</p>
  if (mode === 'dev' && publicRelay && new URLSearchParams(location.search).get('connect') === '1') return <PairPhone kind="guard" onPaired={() => location.replace('/guard')} />
  if (mode === 'dev' && paired) return <GuardApp />
  if (mode === 'dev' && publicRelay) return <PairPhone kind="guard" onPaired={() => setPaired(true)} />
  return <RequireRole roles={['guard']} variant="guard"><GuardApp /></RequireRole>
}

/** /login: after sign-in, send each role to its home. */
function LoginRedirect() {
  const { me } = useSession()
  useEffect(() => {
    const next = new URLSearchParams(location.search).get('next')
    const safeNext = next && next.startsWith('/') && !next.startsWith('//') ? next : null
    location.replace(me?.role === 'guard' ? '/guard' : safeNext ?? '/wall')
  }, [me])
  return <p role="status">Opening NIVRA…</p>
}

export default function App() {
  const [ownerToken] = useState(() => new URLSearchParams(location.hash.slice(1)).get('operator'))
  const route = window.location.pathname
  if (import.meta.env.VITE_NIVRA_USB === '1' && (route === '/' || route === '/setup'))
    return <Suspense fallback={<p role="status">Opening your phones…</p>}><UsbSetup /></Suspense>
  const sample = new URLSearchParams(location.search).get('demo') === '1'
  const fallback = <main className="nv-loading" role="status"><Brand /><p>Getting ready…</p></main>
  if (route === '/usb' || route === '/local') return <Suspense fallback={fallback}><UsbSetup /></Suspense>
  if (ownerToken != null) return <OwnerInvitation token={ownerToken} />
  if (route === '/owner') return <Suspense fallback={fallback}><OwnerAccess /></Suspense>
  if (route === '/') return <Suspense fallback={fallback}><WorkspaceStart /></Suspense>
  if (route === '/mobile') return <Suspense fallback={fallback}><MobileHome /></Suspense>
  if ((route === '/wall' || route === '/guard') && sample)
    return <Suspense fallback={fallback}>{route === '/wall' ? <CommandWall /> : <GuardApp />}</Suspense>
  if (['/wall', '/guard', '/setup', '/login'].includes(route))
    return (
      <AuthRoot>
        <Suspense fallback={fallback}>
          {route === '/guard' ? (
            <GuardAccess />
          ) : route === '/setup' ? (
            <ReleaseRole roles={['admin']}>
              <SetupPortal />
            </ReleaseRole>
          ) : route === '/login' ? (
            <ReleaseRole roles={['admin', 'reviewer', 'guard']}>
              <LoginRedirect />
            </ReleaseRole>
          ) : (
            <ReleaseRole roles={['admin', 'reviewer']}>
              <CommandWall />
            </ReleaseRole>
          )}
        </Suspense>
      </AuthRoot>
    )
  return (
    <Suspense fallback={fallback}>
      {route === '/fight' ? (
        <FightDemo />
      ) : route === '/lab' ? (
        <VisionLab />
      ) : route === '/camera' ? (
        <Publisher />
      ) : (
        <AccessGate>
          <Dashboard />
        </AccessGate>
      )}
    </Suspense>
  )
}
