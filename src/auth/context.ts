import { createContext, useContext } from 'react'
import type { Me, Role } from './session'

export interface AuthState {
  mode: 'clerk' | 'dev'
  /** Provider and /me have settled. */
  ready: boolean
  signedIn: boolean
  me: Me | null
  /** Signed in, but the service refused (no NIVRA role, service down…). */
  problem: string
  refresh: () => Promise<void>
  signOut: () => Promise<void>
  devSignIn: (role: Role, name: string, callsign?: string) => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

/** For surfaces that also run without sign-in (sample workspace). */
export const useOptionalSession = () => useContext(AuthContext)

export function useSession() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useSession must be used inside <AuthRoot>.')
  return value
}
