import { test } from 'node:test'
import assert from 'node:assert/strict'
import worker from './worker.mjs'
const origin = 'https://nivra-vision-lab.topperly.chatgpt.site'
const env = { NIVRA_UPSTREAM: 'https://example.trycloudflare.com', NIVRA_RELAY_SECRET: 'server-only' }
const id = '12345678-1234-4321-abcd-123456789abc'
const hash = 'a'.repeat(64)
const signature = 'b'.repeat(64)
const planPath = `/api/v2/files/plan/${id}`
const framePath = `/api/v2/events/${id}/clip/frames/0`
const planQuery = `?v=${hash}&exp=1900000000&sig=${signature}`
const frameQuery = `?exp=1900000000&sig=${signature}`

test('only exact signed file queries are relayed, with no end-user credentials and correct cache policy', async () => {
  const original = globalThis.fetch
  const captured = []
  globalThis.fetch = async (url, options) => {
    captured.push({ url: String(url), options })
    return new Response('image', { headers: { 'Cache-Control': 'private, max-age=300' } })
  }
  try {
    for (const [path, query, cache] of [
      [planPath, planQuery, 'private, max-age=300'],
      [framePath, frameQuery, 'no-store'],
      [planPath, `?sig=${signature}&v=${hash}&exp=1900000000`, 'private, max-age=300'],
    ]) {
      const response = await worker.fetch(new Request(origin + path + query, {
        headers: { Authorization: 'Bearer ignored', Cookie: 'nivra_operator=ignored; nivra_dev=ignored.signature' },
      }), env)
      assert.equal(response.status, 200)
      assert.equal(response.headers.get('Cache-Control'), cache)
      assert.equal(new URL(captured.at(-1).url).search, query)
      assert.equal(captured.at(-1).options.headers.get('Authorization'), null)
      assert.equal(captured.at(-1).options.headers.get('Cookie'), null)
      assert.equal(captured.at(-1).options.headers.get('X-Nivra-Relay'), 'server-only')
    }
    const before = captured.length
    const denied = [
      planPath, framePath, planPath + frameQuery, framePath + planQuery,
      planPath + planQuery + '&extra=1', planPath + planQuery + '&exp=1900000000',
      planPath + `?v=${hash}&exp=1900000000&exp=1900000000`,
      planPath + planQuery.replace('exp=', '%65xp='),
      planPath + planQuery.replace('1900000000', '-1'),
      planPath + planQuery.replace('1900000000', '1.5'),
      planPath + planQuery.replace('1900000000', '1e9'),
      planPath + planQuery.replace(signature, 'b'.repeat(63)),
      planPath + planQuery.replace(hash, 'g'.repeat(64)),
      planPath + '/' + planQuery, '/api/v2/files/plan/not-a-uuid' + planQuery,
      framePath.replace('/0', '/-1') + frameQuery,
      framePath.replace('/0', '/0extra') + frameQuery,
      '/api/v2/state' + frameQuery, '/setup' + frameQuery,
    ]
    for (const path of denied) assert.equal((await worker.fetch(new Request(origin + path), env)).status, 400, path)
    for (const method of ['POST', 'PATCH', 'DELETE', 'PUT', 'HEAD']) {
      assert.equal((await worker.fetch(new Request(origin + planPath + planQuery, {method, headers: {Origin: origin}}), env)).status, 400)
    }
    assert.equal(captured.length, before)
  } finally { globalThis.fetch = original }
})

test('floor plan PUT alone gets multipart upload budget and preserves bearer authorization', async () => {
  const original = globalThis.fetch
  let captured
  globalThis.fetch = async (url, options) => { captured = {url, options}; return new Response('{}') }
  const path = `/api/v2/floors/${id}/plan`
  const headers = { Origin: origin, 'Content-Type': 'multipart/form-data; boundary=test', Authorization: 'Bearer test.jwt.token' }
  const limit = 8 * 1024 * 1024 + 64 * 1024
  try {
    assert.equal((await worker.fetch(new Request(origin + path, {method: 'PUT', headers, body: new Uint8Array(limit)}), env)).status, 200)
    assert.equal(captured.options.body.size, limit)
    assert.equal(captured.options.headers.get('Authorization'), 'Bearer test.jwt.token')
    assert.equal(captured.options.headers.get('Content-Type'), headers['Content-Type'])
    assert.equal(captured.options.method, 'PUT')
    assert.equal((await worker.fetch(new Request(origin + path, {method: 'PUT', headers, body: new Uint8Array(limit + 1)}), env)).status, 413)
    assert.equal((await worker.fetch(new Request(origin + path, {method: 'PUT', headers: {...headers, 'Content-Length': String(limit + 1)}, body: 'x'}), env)).status, 413)
    for (const denied of [path + '/', path.replace(id, 'invalid'), '/api/v2/members/user_1', '/api/v2/floors']) {
      assert.equal((await worker.fetch(new Request(origin + denied, {method: 'PUT', headers, body: 'x'}), env)).status, 403)
    }
    for (const contentType of ['application/json', 'multipart/form-dataevil', 'text/plain']) {
      assert.equal((await worker.fetch(new Request(origin + path, {method: 'PUT', headers: {...headers, 'Content-Type': contentType}, body: 'x'}), env)).status, 415)
    }
    assert.equal((await worker.fetch(new Request(origin + path + '?extra=1', {method: 'PUT', headers, body: 'x'}), env)).status, 400)
    assert.equal((await worker.fetch(new Request(origin + path, {method: 'PUT', headers: {...headers, Origin: 'https://evil.test'}, body: 'x'}), env)).status, 403)
    assert.equal((await worker.fetch(new Request(origin + '/api/v2/members/invite', {method: 'POST', headers, body: 'x'.repeat(8193)}), env)).status, 413)
  } finally { globalThis.fetch = original }
})

test('auth routes, bearer header, dev cookie and member DELETE survive the relay', async () => {
  const original = globalThis.fetch
  const captured = []
  globalThis.fetch = async (url, options) => {
    captured.push({ url: String(url), options })
    return new Response(null, { status: 204 })
  }
  try {
    for (const path of ['/setup', '/login', '/guard/login']) {
      assert.equal((await worker.fetch(new Request(origin + path), env)).status, 204)
      assert.equal((await worker.fetch(new Request(origin + path), {})).status, 503)
    }
    const response = await worker.fetch(new Request(origin + '/api/v2/members/user_2', {
      method: 'DELETE', headers: { Origin: origin, Authorization: 'Bearer fake.jwt.token',
        Cookie: 'nivra_dev=payload.signature; unrelated=secret' },
    }), env)
    assert.equal(response.status, 204)
    assert.equal(captured.at(-1).options.headers.get('Authorization'), 'Bearer fake.jwt.token')
    assert.equal(captured.at(-1).options.headers.get('Cookie'), 'nivra_dev=payload.signature')
    assert.equal(captured.at(-1).options.method, 'DELETE')
  } finally { globalThis.fetch = original }
})

test('WebSocket upgrade returns the upstream socket unchanged for first-message auth', async () => {
  const original = globalThis.fetch
  const socketResponse = { status: 101, webSocket: { marker: 'upstream' } }
  let options
  globalThis.fetch = async (_url, input) => { options = input; return socketResponse }
  try {
    const response = await worker.fetch(new Request(origin + '/api/v2/operator', {
      headers: { Origin: origin, Upgrade: 'websocket', Authorization: 'Bearer fake.jwt.token' },
    }), env)
    assert.equal(response, socketResponse)
    assert.equal(options.headers.get('Upgrade'), 'websocket')
    assert.equal(options.headers.get('Authorization'), 'Bearer fake.jwt.token')
  } finally { globalThis.fetch = original }
})

test('public relay rejects bootstrap, foreign origins, arbitrary routes and oversized bodies', async () => {
  for (const path of ['/api/v1/session', '/api/v2/operator/invite', '/server/index.js', '/?demo=1']) {
    const response = await worker.fetch(new Request(origin+path), env)
    assert.ok([400,404].includes(response.status))
  }
  assert.equal((await worker.fetch(new Request(origin+'/api/v2/cameras', {method:'POST',headers:{Origin:'https://evil.example'}}),env)).status,403)
  assert.equal((await worker.fetch(new Request(origin+'/api/v2/cameras', {method:'POST',headers:{Origin:origin},body:'x'.repeat(8193)}),env)).status,413)
})
test('relay uses server-held secret and strips attacker headers, without forwarding redirects', async () => {
  const original = globalThis.fetch
  let captured
  globalThis.fetch = async (url, options) => {
    captured = {url,options}
    return new Response(null,{status:302,headers:{Location:'https://bad.example'}})
  }
  try {
    const response = await worker.fetch(new Request(origin+'/api/v2/state', {headers:{'X-Nivra-Relay':'attacker','X-Forwarded-Host':'localhost'}}),env)
    assert.equal(response.status,503)
    assert.equal(captured.options.headers.get('X-Nivra-Relay'),'server-only')
    assert.equal(captured.options.headers.get('X-Forwarded-Host'),null)
    assert.equal(captured.options.redirect,'manual')
  } finally { globalThis.fetch = original }
})

test('fight demo forwards its scoped cookie and reports an offline PC clearly', async () => {
  for (const path of ['/fight', '/wall', '/guard']) {
    const offline = await worker.fetch(new Request(origin+path), {})
    assert.equal(offline.status, 503)
    assert.match(await offline.text(), /Analysis PC offline/)
  }
  const original = globalThis.fetch
  let captured
  globalThis.fetch = async (url, options) => {
    captured = options
    return new Response('{}', {headers:{'Content-Type':'application/json'}})
  }
  try {
    const response = await worker.fetch(new Request(origin+'/api/v2/fight/health', {
      headers:{Cookie:'nivra_fight_session=demo-token; nivra_guard=guard-token; unrelated=do-not-forward'},
    }), env)
    assert.equal(response.status, 200)
    assert.equal(captured.headers.get('Cookie'), 'nivra_fight_session=demo-token; nivra_guard=guard-token')
    for (const path of ['/fight-samples/grappling.webm', '/wall', '/guard']) {
      assert.equal((await worker.fetch(new Request(origin+path), env)).status,200)
    }
  } finally { globalThis.fetch = original }
})
