// Shared auth plumbing for fetch and WebSockets. Clerk tokens are short-lived,
// so callers always ask the provider for a fresh one.

export type Role = 'admin' | 'reviewer' | 'guard'
export interface Me {
  userId: string
  name: string | null
  email: string | null
  role: Role
  guard: { callsign: string } | null
  workspace?: { id: string; name: string; ownerVerification: 'unverified' }
  authMode: 'clerk' | 'dev'
}

type TokenProvider = () => Promise<string | null>
let provider: TokenProvider = async () => null

export function setTokenProvider(next: TokenProvider) {
  provider = next
}
export const sessionToken = () => provider().catch(() => null)

export const clerkKey: string = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? ''
export const authMode: 'clerk' | 'dev' = clerkKey ? 'clerk' : 'dev'

/**
 * Authenticate a socket per the contract: first message within 5 s, then
 * refresh at most every 50 s. Dev mode relies on the cookie but sends the
 * message anyway so both modes share one path.
 */
export function authenticateSocket(socket: WebSocket) {
  let timer = 0
  const send = async () => {
    const token = await sessionToken()
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'auth', token }))
  }
  socket.addEventListener('open', () => {
    void send()
    timer = window.setInterval(() => void send(), 45_000)
  })
  socket.addEventListener('close', () => clearInterval(timer))
}

export const roleLabel = (role: Role) =>
  role === 'admin' ? 'Admin' : role === 'reviewer' ? 'Reviewer' : 'Guard'
