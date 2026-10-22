import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const PUBLIC_ORIGIN = 'https://nivra.tanishq.work'
const ROUTE_KEY = '__nivra_path'
const HOP_HEADERS = ['host', 'content-length', 'connection', 'forwarded', 'x-forwarded-host', 'x-forwarded-for', 'x-forwarded-proto', 'x-nivra-relay', 'transfer-encoding', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer']

// Runtime environment only. No credentials are copied into the deployment artifact.
export function createRelay({ env = process.env, fetchImpl = fetch } = {}) {
  return async function relay(request, output) {
    const fail = (detail, status) => {
      output.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
      output.end(JSON.stringify({ detail }))
    }
    const source = new URL(request.url, PUBLIC_ORIGIN)
    if (source.pathname === '/__nivra_relay' || source.searchParams.has(ROUTE_KEY)) {
      const paths = source.searchParams.getAll(ROUTE_KEY)
      if (paths.length !== 1 || !paths[0].startsWith('/api/')) return fail('Route unavailable.', 404)
      // Some routing adapters retain the original pathname after a rewrite.
      if (source.pathname !== '/__nivra_relay' && source.pathname !== paths[0]) return fail('Route unavailable.', 404)
      source.pathname = paths[0]
      source.searchParams.delete(ROUTE_KEY)
    }
    if (!source.pathname.startsWith('/api/v2/') || source.pathname === '/api/v2/operator/invite') return fail('Route unavailable.', 404)
    if (request.headers.upgrade) return fail('Use an authenticated direct socket ticket.', 426)
    if (!['GET', 'HEAD'].includes(request.method) && request.headers.origin !== PUBLIC_ORIGIN) return fail('Origin rejected.', 403)
    const upstream = env.NIVRA_UPSTREAM
    const secret = env.NIVRA_RELAY_SECRET
    if (!upstream || !secret) return fail('The NIVRA relay is not connected.', 503)
    let target
    try {
      target = new URL(upstream)
      if (target.protocol !== 'https:' || !target.hostname.endsWith('.trycloudflare.com') || target.username || target.password || target.port || target.pathname !== '/' || target.search || target.hash) throw new Error()
    } catch { return fail('The relay connection needs attention.', 503) }
    target.pathname = source.pathname
    target.search = source.search
    const headers = new Headers()
    for (const [name, value] of Object.entries(request.headers)) {
      if (value !== undefined && !HOP_HEADERS.includes(name.toLowerCase())) headers.set(name, Array.isArray(value) ? value.join(', ') : value)
    }
    headers.set('X-Nivra-Relay', secret)
    // Node fetch decodes compressed bodies. Ask for identity and remove encoding
    // headers below so forwarded binary bytes always match their representation.
    headers.set('Accept-Encoding', 'identity')
    let body
    if (!['GET', 'HEAD'].includes(request.method)) {
      const limit = source.pathname.endsWith('/plan') && request.method === 'PUT' ? 8 * 1024 * 1024 + 65536 : 16384
      if (Number(request.headers['content-length']) > limit) return fail('Request too large.', 413)
      const chunks = []
      let size = 0
      try {
        for await (const chunk of request) {
          size += chunk.length
          if (size > limit) return fail('Request too large.', 413)
          chunks.push(chunk)
        }
      } catch { return fail('Request interrupted.', 400) }
      body = Buffer.concat(chunks)
    }
    try {
      const response = await fetchImpl(target, { method: request.method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(25000) })
      const responseHeaders = {}
      response.headers.forEach((value, name) => {
        if (!HOP_HEADERS.includes(name) && !['set-cookie', 'content-encoding'].includes(name)) responseHeaders[name] = value
      })
      const cookies = response.headers.getSetCookie()
      if (cookies.length) responseHeaders['set-cookie'] = cookies
      responseHeaders['cache-control'] = 'no-store'
      responseHeaders['referrer-policy'] = 'no-referrer'
      responseHeaders['x-content-type-options'] = 'nosniff'
      output.writeHead(response.status, responseHeaders)
      if (response.body && request.method !== 'HEAD') await pipeline(Readable.fromWeb(response.body), output)
      else output.end()
    } catch {
      if (output.headersSent) output.destroy()
      else fail('The NIVRA relay is offline. Keep the host service running.', 503)
    }
  }
}

export default createRelay()
