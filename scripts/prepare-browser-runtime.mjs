import { copyFile, mkdir, readFile, rm } from 'node:fs/promises'
import { createHash } from 'node:crypto'

// Keep the loader and WASM from the same pinned package, on our own origin.
// The worker must not depend on a CDN being reachable after the page opens.
const source = new URL('../node_modules/onnxruntime-web/', import.meta.url)
const target = new URL('../public/onnxruntime/', import.meta.url)
const metadata = JSON.parse(await readFile(new URL('package.json', source), 'utf8'))
if (metadata.version !== '1.30.0') throw new Error('Unexpected browser inference runtime version')
await mkdir(target, { recursive: true })
// Only the validated CPU backend ships. GPU candidates failed output parity.
for (const variant of ['.jsep', '.asyncify', '.jspi'])
  for (const extension of ['mjs', 'wasm']) {
    const file = `ort-wasm-simd-threaded${variant}.${extension}`
    await rm(new URL(file, target), { force: true })
  }
for (const file of ['ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.wasm'])
  await copyFile(new URL(`dist/${file}`, source), new URL(file, target))
const model = await readFile(new URL('../public/models/rtmo-t-body7-416-20aad6e2.onnx', import.meta.url))
if (createHash('sha256').update(model).digest('hex') !== '20aad6e2e42359cac1c5b4a0b2da00e29bfe91a72a782fdcf287d273a04c1b24')
  throw new Error('Crowd model does not match the validated checksum')
