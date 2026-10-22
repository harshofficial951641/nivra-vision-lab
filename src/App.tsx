import { lazy, Suspense, useEffect } from 'react'
import AccessGate from './classroom/AccessGate'
import { AuthRoot } from './auth/AuthRoot'
import { RequireRole } from './auth/RequireRole'
import { useSession } from './auth/context'
const VisionLab = lazy(() => import('./VisionLab'))
const Dashboard = lazy(() => import('./classroom/Dashboard'))
const Publisher = lazy(() => import('./classroom/Publisher'))
const FightDemo = lazy(() => import('./FightDemo'))
const CommandWall = lazy(() => import('./command/CommandWall'))
const GuardApp = lazy(() => import('./guard/GuardApp'))
const SetupPortal = lazy(() => import('./setup/SetupPortal'))

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
  const route = window.location.pathname
  const sample = new URLSearchParams(location.search).get('demo') === '1'
  const fallback = <p role="status">Opening NIVRA…</p>
  if ((route === '/wall' || route === '/guard') && sample)
    return <Suspense fallback={fallback}>{route === '/wall' ? <CommandWall /> : <GuardApp />}</Suspense>
  if (['/wall', '/guard', '/setup', '/login'].includes(route))
    return (
      <AuthRoot>
        <Suspense fallback={fallback}>
          {route === '/guard' ? (
            <RequireRole roles={['guard']} variant="guard">
              <GuardApp />
            </RequireRole>
          ) : route === '/setup' ? (
            <RequireRole roles={['admin']} variant="reviewer">
              <SetupPortal />
            </RequireRole>
          ) : route === '/login' ? (
            <RequireRole roles={['admin', 'reviewer', 'guard']} variant="reviewer">
              <LoginRedirect />
            </RequireRole>
          ) : (
            <RequireRole roles={['admin', 'reviewer']} variant="reviewer">
              <CommandWall />
            </RequireRole>
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
