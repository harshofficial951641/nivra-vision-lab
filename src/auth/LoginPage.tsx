import { useState, type FormEvent, type ReactNode } from 'react'
import { SignIn } from '@clerk/clerk-react'
import { useSession } from './context'
import { roleLabel, type Role } from './session'
import './auth.css'

type Variant = 'reviewer' | 'guard'

const copy = {
  reviewer: {
    eyebrow: 'Command',
    title: 'Reviewer sign-in',
    lead: 'Watch the cameras, review incidents and alert guards.',
    other: { href: '/guard', label: 'Are you a guard? Open the guard app' },
  },
  guard: {
    eyebrow: 'Guard',
    title: 'Guard sign-in',
    lead: 'Sign in on your own phone to receive alerts during your shift.',
    other: { href: '/login', label: 'Reviewer? Sign in to Command' },
  },
}

const clerkAppearance = (dark: boolean) => ({
  variables: {
    colorPrimary: dark ? '#fafafa' : '#09090b',
    colorText: dark ? '#fafafa' : '#09090b',
    colorTextOnPrimaryBackground: dark ? '#09090b' : '#ffffff',
    colorBackground: dark ? '#18181b' : '#ffffff',
    colorInputBackground: dark ? '#27272a' : '#ffffff',
    colorInputText: dark ? '#fafafa' : '#09090b',
    borderRadius: '8px',
    fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif",
  },
  elements: {
    card: { boxShadow: 'none', border: dark ? '1px solid #3f3f46' : '1px solid #e4e4e7' },
    footer: { display: 'none' },
  },
})

function DevSignIn({ variant }: { variant: Variant }) {
  const { devSignIn } = useSession()
  const [role, setRole] = useState<Role>(variant === 'guard' ? 'guard' : 'admin')
  const [name, setName] = useState(variant === 'guard' ? 'Rohan' : 'Harsh')
  const [callsign, setCallsign] = useState('G2')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await devSignIn(role, name.trim() || roleLabel(role), role === 'guard' ? callsign.trim().toUpperCase() : undefined)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="au-dev" onSubmit={(e) => void submit(e)}>
      <p className="au-note">
        <strong>Developer sign-in.</strong> Clerk keys are not configured on this build, so anyone who can open this page
        can choose a role. Use it only for local demos.
      </p>
      <fieldset>
        <legend>Role</legend>
        <div className="au-roles">
          {(variant === 'guard' ? (['guard'] as Role[]) : (['admin', 'reviewer'] as Role[])).map((r) => (
            <label key={r} className={role === r ? 'is-on' : ''}>
              <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} />
              {roleLabel(r)}
            </label>
          ))}
        </div>
      </fieldset>
      {role !== 'guard' && (
        <label className="au-field">
          <span>Name</span>
          <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
        </label>
      )}
      {role === 'guard' && (
        <label className="au-field">
          <span>Call sign</span>
          <input
            value={callsign}
            maxLength={3}
            pattern="[Gg][0-9]{1,2}"
            title="G followed by a number, for example G2"
            onChange={(e) => setCallsign(e.target.value)}
            required
          />
        </label>
      )}
      {error && (
        <p className="au-error" role="alert">
          {error}
        </p>
      )}
      <button className="au-submit" disabled={busy}>
        {busy ? 'Signing in…' : 'Continue'}
      </button>
    </form>
  )
}

export function LoginPage({ variant }: { variant: Variant }) {
  const { mode } = useSession()
  const text = copy[variant]
  const dark = variant === 'guard'
  return (
    <main className={`au-page ${dark ? 'au-page--dark' : ''}`}>
      <section className="au-panel" aria-labelledby="login-title">
        <p className="au-brand">NIVRA</p>
        <p className="au-eyebrow">{text.eyebrow}</p>
        <h1 id="login-title">{text.title}</h1>
        <p className="au-lead">{text.lead}</p>
        {mode === 'clerk' ? (
          <SignIn routing="hash" appearance={clerkAppearance(dark)} />
        ) : (
          <DevSignIn variant={variant} />
        )}
        <a className="au-other" href={text.other.href}>
          {text.other.label}
        </a>
      </section>
    </main>
  )
}

export function AccessMessage({
  title,
  children,
  dark,
  action,
}: {
  title: string
  children: ReactNode
  dark?: boolean
  action?: ReactNode
}) {
  return (
    <main className={`au-page ${dark ? 'au-page--dark' : ''}`}>
      <section className="au-panel" role="alert">
        <p className="au-brand">NIVRA</p>
        <h1>{title}</h1>
        <div className="au-lead">{children}</div>
        {action}
      </section>
    </main>
  )
}
