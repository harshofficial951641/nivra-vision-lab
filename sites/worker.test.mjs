import { test } from 'node:test'
import assert from 'node:assert/strict'
import worker from './worker.mjs'
const origin = 'https://nivra-vision-lab.topperly.chatgpt.site'
const env = { NIVRA_UPSTREAM: 'https://example.trycloudflare.com', NIVRA_RELAY_SECRET: 'server-only' }
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
  const offline = await worker.fetch(new Request(origin+'/fight'), {})
  assert.equal(offline.status, 503)
  assert.match(await offline.text(), /Analysis PC offline/)
  const original = globalThis.fetch
  let captured
  globalThis.fetch = async (url, options) => {
    captured = options
    return new Response('{}', {headers:{'Content-Type':'application/json'}})
  }
  try {
    const response = await worker.fetch(new Request(origin+'/api/v2/fight/health', {
      headers:{Cookie:'nivra_fight_session=demo-token; unrelated=do-not-forward'},
    }), env)
    assert.equal(response.status, 200)
    assert.equal(captured.headers.get('Cookie'), 'nivra_fight_session=demo-token')
    assert.equal((await worker.fetch(new Request(origin+'/fight-samples/grappling.webm'), env)).status,200)
  } finally { globalThis.fetch = original }
})
