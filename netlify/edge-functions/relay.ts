// HTTP stays on our origin so scoped HttpOnly cookies work in browsers and apps.
// Streaming WebSockets use one-use capabilities and connect directly to the relay.
export default async function relay(request: Request) {
  const source = new URL(request.url)
  const fail = (detail: string, status: number) => Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } })
  if (!source.pathname.startsWith('/api/v2/') || source.pathname === '/api/v2/operator/invite') return fail('Route unavailable.', 404)
  if (request.headers.get('upgrade')) return fail('Use an authenticated direct socket ticket.', 426)
  const publicOrigin = 'https://nivra.tanishq.work'
  if (!['GET', 'HEAD'].includes(request.method) && request.headers.get('origin') !== publicOrigin) return fail('Origin rejected.', 403)
  const upstream = Netlify.env.get('NIVRA_UPSTREAM')
  const secret = Netlify.env.get('NIVRA_RELAY_SECRET')
  if (!upstream || !secret) return fail('The NIVRA relay is not connected.', 503)
  let target: URL
  try {
    target = new URL(upstream)
    if (target.protocol !== 'https:' || !target.hostname.endsWith('.trycloudflare.com') || target.username || target.password || target.port || target.pathname !== '/' || target.search || target.hash) throw new Error()
  } catch { return fail('The relay connection needs attention.', 503) }
  target.pathname = source.pathname
  target.search = source.search
  const headers = new Headers(request.headers)
  for (const name of ['host', 'content-length', 'connection', 'forwarded', 'x-forwarded-host', 'x-forwarded-for', 'x-forwarded-proto', 'x-nivra-relay']) headers.delete(name)
  headers.set('X-Nivra-Relay', secret)
  let body: ArrayBuffer | undefined
  if (!['GET', 'HEAD'].includes(request.method)) {
    const limit = source.pathname.endsWith('/plan') && request.method === 'PUT' ? 8 * 1024 * 1024 + 65536 : 16384
    if (Number(request.headers.get('content-length')) > limit) return fail('Request too large.', 413)
    body = await request.arrayBuffer()
    if (body.byteLength > limit) return fail('Request too large.', 413)
  }
  try {
    const response = await fetch(target, { method: request.method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(25000) })
    const output = new Response(response.body, response)
    output.headers.set('Cache-Control', 'no-store')
    output.headers.set('Referrer-Policy', 'no-referrer')
    output.headers.set('X-Content-Type-Options', 'nosniff')
    return output
  } catch { return fail('The NIVRA relay is offline. Keep the host service running.', 503) }
}
export const config = { path: '/api/*', cache: 'manual' }
