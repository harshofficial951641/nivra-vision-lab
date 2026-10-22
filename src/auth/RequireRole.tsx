import type { ReactNode } from 'react'
import { useSession } from './context'
import { AccessMessage, LoginPage } from './LoginPage'
import { roleLabel, type Role } from './session'

export function RequireRole({
  roles,
  variant,
  children,
}: {
  roles: Role[]
  variant: 'reviewer' | 'guard'
  children: ReactNode
}) {
  const { ready, signedIn, me, problem, signOut, refresh } = useSession()
  const dark = variant === 'guard'
  if (!ready)
    return (
      <main className={`au-page ${dark ? 'au-page--dark' : ''}`}>
        <p role="status">Checking your sign-in…</p>
      </main>
    )
  if (!signedIn) return <LoginPage variant={variant} />
  if (!me) {
    const noRole = problem === 'no-role'
    return (
      <AccessMessage
        dark={dark}
        title={noRole ? 'No NIVRA access yet' : 'Can’t reach NIVRA'}
        action={
          <div className="au-actions">
            <button className="au-submit" onClick={() => void refresh()}>
              Try again
            </button>
            <button className="au-secondary" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
        }
      >
        {noRole ? 'You are signed in, but an admin has not given this account a role. Ask them to invite you from Setup → People.' : problem}
      </AccessMessage>
    )
  }
  if (!roles.includes(me.role)) {
    const target = me.role === 'guard' ? { href: '/guard', label: 'Open the guard app' } : { href: '/wall', label: 'Open Command' }
    return (
      <AccessMessage
        dark={dark}
        title={`Signed in as ${roleLabel(me.role)}`}
        action={
          <div className="au-actions">
            <a className="au-submit" href={target.href}>
              {target.label}
            </a>
            <button className="au-secondary" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
        }
      >
        This page is for {roles.map(roleLabel).join(' or ').toLowerCase()} accounts.
      </AccessMessage>
    )
  }
  return children
}
