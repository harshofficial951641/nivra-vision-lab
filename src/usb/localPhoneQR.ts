export type LocalPhonePair = { host: string; hosts?: string[]; code: string }
const privateIPv4 = (value: string) => {
  const pieces = value.split('.')
  if (pieces.length !== 4 || pieces.some(piece => !/^(0|[1-9][0-9]{0,2})$/.test(piece) || Number(piece) > 255)) return false
  const [a, b] = pieces.map(Number)
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
}
/** Parse a phone capability without navigating or contacting the QR's address. */
export function localPhoneQR(value: string): LocalPhonePair | null {
  try {
    const url = new URL(value.trim())
    const query = url.searchParams, fragment = new URLSearchParams(url.hash.slice(1))
    if (url.protocol !== 'nivra-local:' || url.hostname !== 'camera' || url.pathname || url.username || url.password || url.port) return null
    if ([...query.keys()].some(key => !['host', 'hosts', 'port'].includes(key)) || [...fragment.keys()].some(key => key !== 'key')) return null
    if (query.getAll('host').length !== 1 || query.getAll('port').length !== 1 || query.getAll('hosts').length > 1 || fragment.getAll('key').length !== 1) return null
    const host = query.get('host')!, code = fragment.get('key')!
    if (!privateIPv4(host) || query.get('port') !== '8940' || !/^[A-HJ-NP-Z2-9]{8}$/.test(code)) return null
    const values = query.has('hosts') ? query.get('hosts')!.split(',') : [host]
    if (!values.length || values.length > 8 || new Set(values).size !== values.length || !values.includes(host) || values.some(value => !privateIPv4(value))) return null
    return { host, ...(values.length > 1 ? { hosts: values } : {}), code }
  } catch { return null }
}
