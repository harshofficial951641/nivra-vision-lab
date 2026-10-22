/** Pairing links stay on this deployment and keep their original role. */
export function pairingDestination(value: string, origin: string): string | null {
  try {
    const url = new URL(value.trim(), origin)
    const owner = ['/', '/wall'].includes(url.pathname)
    const token = new URLSearchParams(url.hash.slice(1)).get(owner ? 'operator' : 'pair')
    if (url.origin !== origin || !['/camera', '/guard', '/wall', '/'].includes(url.pathname) ||
      !token || !/^[A-Za-z0-9_-]{30,100}$/.test(token) || url.username || url.password) return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch { return null }
}
