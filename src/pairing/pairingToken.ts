import { pairingDestination } from '../mobile/pairingDestination'

/** Only exchange a matching device capability. A scanned owner link grants nothing here. */
export function tokenForPhone(value: string, kind: 'camera' | 'guard', origin: string): string | null {
  const destination = pairingDestination(value, origin)
  if (!destination) return null
  const url = new URL(destination, origin)
  if (url.pathname !== `/${kind}`) return null
  const fields = new URLSearchParams(url.hash.slice(1))
  const tokens = fields.getAll('pair')
  return tokens.length === 1 && !fields.has('operator') ? tokens[0] : null
}
