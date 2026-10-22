// The Site relays to the owner's PC. No frame, cookie or payload is logged or stored.
const PUBLIC_ORIGIN = 'https://nivra-vision-lab.topperly.chatgpt.site'
const UUID = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
const PLAN_FILE = new RegExp(`^/api/v2/files/plan/${UUID}$`)
const CLIP_FRAME = new RegExp(`^/api/v2/events/${UUID}/clip/frames/[0-9]+$`)
const PLAN_UPLOAD = new RegExp(`^/api/v2/floors/${UUID}/plan$`)
const HEX64 = /^[0-9a-fA-F]{64}$/
const INTEGER = /^[0-9]+$/

function validSignedQuery(search, plan) {
  const expected = plan ? ['v', 'exp', 'sig'] : ['exp', 'sig']
  const parts = search.slice(1).split('&')
  if (!search.startsWith('?') || parts.length !== expected.length) return false
  const seen = new Set()
  for (const part of parts) {
    // Validate raw query text: no duplicate, encoded, or extra parameter names.
    const pair = /^([a-z]+)=([0-9a-fA-F]+)$/.exec(part)
    if (!pair || !expected.includes(pair[1]) || seen.has(pair[1])) return false
    if (!(pair[1] === 'exp' ? INTEGER : HEX64).test(pair[2])) return false
    seen.add(pair[1])
  }
  return true
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url)
    const error = (detail, status) => {
      if (status === 503 && ['/', '/camera', '/lab', '/fight', '/wall', '/guard', '/setup', '/login', '/guard/login'].includes(url.pathname)) return new Response(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Nivra · Analysis PC offline</title><style>body{font:16px/1.6 system-ui;background:#f6f7f8;color:#18181b;display:grid;place-items:center;min-height:90vh;margin:24px}main{max-width:480px;padding:32px;background:white;border:1px solid #ddd;border-radius:12px}a{color:inherit}</style><main><strong>NIVRA</strong><h1>Analysis PC offline</h1><p>Keep the Nivra analysis service and public bridge running on your PC. Live cameras and review records will reconnect when it is back online.</p><a href="/">Try connecting again</a></main></html>',
        {status,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','Referrer-Policy':'no-referrer'}})
      return Response.json({ detail }, { status, headers: { 'Cache-Control': 'no-store' } })
    }
    if (url.pathname === '/favicon.ico') return new Response(null, {status:204})
    const api = url.pathname.startsWith('/api/v2/')
    const allowed = api && url.pathname !== '/api/v2/operator/invite' || request.method === 'GET' && (
      ['/', '/camera', '/lab', '/fight', '/wall', '/guard', '/setup', '/login', '/guard/login', '/favicon.svg'].includes(url.pathname) ||
      ['/assets/', '/brand/', '/models/', '/mediapipe/', '/fight-samples/'].some(p => url.pathname.startsWith(p)))
    if (!allowed) return error('This route is unavailable on the public site.', 404)
    const planFile = PLAN_FILE.test(url.pathname)
    const signedFile = planFile || CLIP_FRAME.test(url.pathname)
    if (signedFile && (request.method !== 'GET' || request.headers.get('Upgrade') || !validSignedQuery(url.search, planFile)))
      return error('Invalid signed file request.', 400)
    if (url.search && !signedFile) return error('Query parameters are not supported.', 400)
    const planUpload = request.method === 'PUT' && PLAN_UPLOAD.test(url.pathname)
    if (api && ((!['GET', 'POST', 'PATCH', 'DELETE'].includes(request.method) && !planUpload) ||
      (request.method !== 'GET' || request.headers.get('Upgrade')) && request.headers.get('Origin') !== PUBLIC_ORIGIN))
      return error('Origin rejected.', 403)
    if (planUpload && !/^multipart\/form-data(?:\s*;|$)/i.test(request.headers.get('Content-Type') || ''))
      return error('Use multipart/form-data for floor plans.', 415)
    if (!env.NIVRA_UPSTREAM || !env.NIVRA_RELAY_SECRET) return error('The analysis PC is not connected.', 503)
    let upstream
    try {
      upstream = new URL(env.NIVRA_UPSTREAM)
      if (upstream.protocol !== 'https:' || !upstream.hostname.endsWith('.trycloudflare.com') || upstream.username || upstream.password)
        throw new Error('Invalid upstream')
    } catch { return error('The analysis PC connection needs attention.', 503) }
    upstream.pathname = url.pathname
    upstream.search = signedFile ? url.search : ''
    const headers = new Headers()
    for (const name of ['Authorization', 'Origin', 'Content-Type', 'Upgrade', 'Sec-WebSocket-Key', 'Sec-WebSocket-Version', 'Sec-WebSocket-Protocol', 'Sec-Fetch-Site']) {
      if (signedFile && name === 'Authorization') continue
      const value = request.headers.get(name)
      if (value) headers.set(name, value)
    }
    const cookies = (request.headers.get('Cookie') || '').split(';').map(v => v.trim())
      .filter(v => /^(nivra_operator|nivra_publisher|nivra_fight_session|nivra_guard|nivra_dev)=[A-Za-z0-9_.-]+$/.test(v)).join('; ')
    if (cookies && !signedFile) headers.set('Cookie', cookies)
    headers.set('X-Nivra-Relay', env.NIVRA_RELAY_SECRET)
    let body
    if (!['GET', 'HEAD'].includes(request.method)) {
      const limit = planUpload ? 8 * 1024 * 1024 + 64 * 1024 : 8192
      if (Number(request.headers.get('Content-Length')) > limit) return error('Request too large.', 413)
      const reader = request.body?.getReader()
      const chunks = []; let size = 0
      if (reader) while (true) {
        const next = await reader.read()
        if (next.done) break
        size += next.value.length
        if (size > limit) { await reader.cancel(); return error('Request too large.', 413) }
        chunks.push(next.value)
      }
      body = new Blob(chunks)
    }
    try {
      const response = await fetch(upstream, { method: request.method, headers, body, redirect: 'manual' })
      if (response.status === 101) return response
      if (response.status >= 500 || response.status >= 300 && response.status < 400)
        return error('The analysis PC is offline or reconnecting. Keep its public bridge running.', 503)
      const output = new Response(response.body, response)
      if (!(planFile && response.ok && response.headers.has('Cache-Control')))
        output.headers.set('Cache-Control', 'no-store')
      output.headers.set('Referrer-Policy', 'no-referrer')
      output.headers.set('X-Content-Type-Options', 'nosniff')
      output.headers.set('Permissions-Policy', 'camera=(self), microphone=()')
      return output
    } catch { return error('The analysis PC is offline. Keep its public bridge running.', 503) }
  }
}
