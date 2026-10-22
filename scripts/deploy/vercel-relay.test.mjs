import test from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { createRelay } from './vercel-relay.mjs'

async function server(handler) {
  const instance = http.createServer(handler)
  await new Promise(resolve => instance.listen(0, '127.0.0.1', resolve))
  return { url: `http://127.0.0.1:${instance.address().port}`, close: () => new Promise(resolve => instance.close(resolve)) }
}
const env = { NIVRA_UPSTREAM: 'https://example.trycloudflare.com', NIVRA_RELAY_SECRET: 'server-only-test-value' }

test('real HTTP relay preserves cookies, binary, status, POST and redirect without leaking credential', async () => {
  const seen = []
  const upstream = await server(async (req, res) => {
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    seen.push({ url: req.url, headers: req.headers, method: req.method, body: Buffer.concat(chunks) })
    if (req.url === '/api/v2/redirect') {
      res.writeHead(302, { Location: 'https://example.org/next' }); res.end(); return
    }
    res.writeHead(201, {
      'Content-Type': 'application/octet-stream',
      'Set-Cookie': ['session=owner; Path=/api/v2; HttpOnly; Secure; SameSite=Strict', 'guard=one; Path=/; HttpOnly; Secure'],
    })
    res.end(Buffer.from([0, 255, 128, 1]))
  })
  const relay = await server(createRelay({ env, fetchImpl: (target, options) => {
    assert.equal(target.origin, env.NIVRA_UPSTREAM)
    return fetch(upstream.url + target.pathname + target.search, options)
  } }))
  try {
    const response = await fetch(relay.url + '/__nivra_relay?__nivra_path=/api/v2/cameras&since=42', {
      headers: { Cookie: 'session=abc', 'X-Nivra-Relay': 'attacker', 'X-Forwarded-Host': 'evil.example' },
    })
    assert.equal(response.status, 201)
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), Buffer.from([0, 255, 128, 1]))
    assert.equal(response.headers.getSetCookie().length, 2)
    assert.match(response.headers.getSetCookie()[0], /HttpOnly; Secure; SameSite=Strict/)
    assert.equal(response.headers.get('cache-control'), 'no-store')
    assert.equal(response.headers.get('x-nivra-relay'), null)
    assert.equal(seen[0].url, '/api/v2/cameras?since=42')
    assert.equal(seen[0].headers.cookie, 'session=abc')
    assert.equal(seen[0].headers['x-nivra-relay'], env.NIVRA_RELAY_SECRET)
    assert.equal(seen[0].headers['x-forwarded-host'], undefined)
    await fetch(relay.url + '/api/v2/pair', { method: 'POST', headers: { Origin: 'https://nivra.tanishq.work', 'Content-Type': 'application/json' }, body: '{"token":"example"}' })
    assert.equal(seen[1].method, 'POST')
    assert.equal(seen[1].body.toString(), '{"token":"example"}')
    const redirect = await fetch(relay.url + '/api/v2/redirect', { redirect: 'manual' })
    assert.equal(redirect.status, 302)
    assert.equal(redirect.headers.get('location'), 'https://example.org/next')
  } finally { await relay.close(); await upstream.close() }
})

test('relay enforces existing edge gates before upstream fetch', async () => {
  let calls = 0
  const relay = await server(createRelay({ env, fetchImpl: () => { calls++; throw new Error('unreachable') } }))
  try {
    for (const pathname of ['/api/v2/operator/invite', '/api/v1/health', '/__nivra_relay?__nivra_path=/api/v2/operator/invite', '/__nivra_relay?__nivra_path=/api/v2/cameras&__nivra_path=/api/v2/health']) {
      assert.equal((await fetch(relay.url + pathname)).status, 404)
    }
    assert.equal((await fetch(relay.url + '/api/v2/pair', { method: 'POST', headers: { Origin: 'https://evil.example' }, body: '{}' })).status, 403)
    assert.equal((await fetch(relay.url + '/api/v2/pair', { method: 'POST', headers: { Origin: 'https://nivra.tanishq.work' }, body: 'x'.repeat(16385) })).status, 413)
    assert.equal(calls, 0)
  } finally { await relay.close() }
})

test('missing credentials and non Cloudflare upstream fail closed', async () => {
  for (const config of [{}, { ...env, NIVRA_UPSTREAM: 'https://example.com' }, { ...env, NIVRA_UPSTREAM: 'https://example.trycloudflare.com/other' }]) {
    const relay = await server(createRelay({ env: config, fetchImpl: () => { throw new Error('must not fetch') } }))
    try { assert.equal((await fetch(relay.url + '/api/v2/health')).status, 503) }
    finally { await relay.close() }
  }
})

test('a stalled upstream fails within the relay budget and cancels its request', async () => {
  let disconnected = false
  const upstream = await server((_req, res) => { res.on('close', () => { disconnected = true }) })
  const relay = await server(createRelay({ env, upstreamTimeoutMs: 150,
    fetchImpl: (target, options) => fetch(upstream.url + target.pathname, options) }))
  try {
    const began = Date.now()
    const response = await fetch(relay.url + '/api/v2/state')
    assert.equal(response.status, 503)
    assert.ok(Date.now() - began < 2000)
    await response.arrayBuffer()
    for (let n = 0; n < 20 && !disconnected; n++) await new Promise(resolve => setTimeout(resolve, 10))
    assert.equal(disconnected, true)
  } finally { await relay.close(); await upstream.close() }
})

test('disconnecting a browser cancels the old upstream ticket attempt', async () => {
  let markStarted
  const started = new Promise(resolve => { markStarted = resolve })
  let disconnected = false
  const upstream = await server((_req, res) => { res.on('close', () => { disconnected = true }); markStarted() })
  const relay = await server(createRelay({ env,
    fetchImpl: (target, options) => fetch(upstream.url + target.pathname, options) }))
  let request
  try {
    request = http.request(relay.url + '/api/v2/camera/socket-ticket', {
      method: 'POST', headers: { Origin: 'https://nivra.tanishq.work', 'Content-Type': 'application/json' },
    })
    request.on('error', () => {})
    request.end('{}')
    await started
    request.destroy()
    for (let n = 0; n < 50 && !disconnected; n++) await new Promise(resolve => setTimeout(resolve, 10))
    assert.equal(disconnected, true)
  } finally { request?.destroy(); await relay.close(); await upstream.close() }
})
