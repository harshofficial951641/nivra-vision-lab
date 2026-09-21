import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const mediapipeWasmDirectory = fileURLToPath(
  new URL('./public/mediapipe/wasm/', import.meta.url),
)
const mediapipeWasmFiles = new Set([
  'vision_wasm_internal.js',
  'vision_wasm_internal.wasm',
  'vision_wasm_module_internal.js',
  'vision_wasm_module_internal.wasm',
  'vision_wasm_nosimd_internal.js',
  'vision_wasm_nosimd_internal.wasm',
])

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'nivra-mediapipe-dev-assets',
      configureServer(server) {
        server.middlewares.use('/__nivra_wasm', (request, response, next) => {
          const fileName = request.url?.split('?')[0].split('/').pop()
          if (!fileName || !mediapipeWasmFiles.has(fileName)) {
            next()
            return
          }

          response.statusCode = 200
          response.setHeader(
            'Content-Type',
            fileName.endsWith('.wasm') ? 'application/wasm' : 'text/javascript',
          )
          response.end(readFileSync(`${mediapipeWasmDirectory}${fileName}`))
        })
      },
    },
  ],
  optimizeDeps: {
    exclude: ['@mediapipe/tasks-vision'],
  },
  worker: {
    format: 'es',
  },
  server: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
  preview: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
})
