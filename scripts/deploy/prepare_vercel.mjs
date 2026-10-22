import { access, cp, mkdir, rm, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('../../', import.meta.url))
const output = path.join(root, '.vercel/output')
await access(path.join(root, 'dist/index.html'))
await rm(output, { recursive: true, force: true })
await mkdir(path.join(output, 'functions/__nivra_relay.func'), { recursive: true })
await cp(path.join(root, 'dist'), path.join(output, 'static'), { recursive: true })
await cp(new URL('./vercel-relay.mjs', import.meta.url), path.join(output, 'functions/__nivra_relay.func/index.mjs'))
const json = (file, value) => writeFile(path.join(output, file), JSON.stringify(value, null, 2) + '\n')
await json('functions/__nivra_relay.func/.vc-config.json', {
  runtime: 'nodejs24.x', handler: 'index.mjs', launcherType: 'Nodejs',
  supportsResponseStreaming: true, maxDuration: 30,
})
await json('config.json', {
  version: 3,
  routes: [
    { src: '/(.*)', headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
      'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
      'Permissions-Policy': 'camera=(self), geolocation=(self), microphone=()',
    }, continue: true },
    { src: '/\\.well-known/(.*)', headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=300' }, continue: true },
    { src: '/api/(.*)', dest: '/__nivra_relay?__nivra_path=/api/$1' },
    { handle: 'filesystem' },
    { src: '/(.*)', dest: '/index.html' },
  ],
})
console.log('Prepared .vercel/output. Runtime needs NIVRA_UPSTREAM and NIVRA_RELAY_SECRET.')
