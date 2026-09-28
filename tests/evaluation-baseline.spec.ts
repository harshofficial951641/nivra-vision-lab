import { test, expect } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve, dirname } from 'node:path'
import { createHash } from 'node:crypto'
import { ConflictEngine } from '../src/lib/conflictEngine'
import type { PoseLandmarks } from '../src/types/vision'

test.use({ video: 'off', trace: 'off' })
test('evaluate the unchanged browser rules on the frozen corpus', async ({ browser }) => {
  test.skip(!process.env.NIVRA_EVAL_MANIFEST, 'Opt-in licensed footage evaluation')
  test.setTimeout(900_000)
  const manifest = resolve(process.env.NIVRA_EVAL_MANIFEST!)
  const bytes = await readFile(manifest)
  const clips = JSON.parse(bytes.toString()) as Array<{ id: string; path: string; crop?: number[]; sha256: string }>
  const report = { backend: 'browser-mediapipe-full-cpu-standard', manifestSha256: createHash('sha256').update(bytes).digest('hex'), clips: {} as Record<string, unknown> }
  for (const clip of clips) {
    const context = await browser.newContext({ baseURL: 'http://127.0.0.1:4173' })
    const page = await context.newPage()
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
    const path = resolve(dirname(manifest), clip.path)
    expect(createHash('sha256').update(await readFile(path)).digest('hex')).toBe(clip.sha256)
    await page.addInitScript(({ crop }) => {
      const frames: Array<{ timestampMs: number; poses: PoseLandmarks[]; aspect: number }> = []
      Object.assign(window, { __baselineFrames: frames })
      const NativeWorker = window.Worker
      window.Worker = class extends NativeWorker {
        constructor(url: string | URL, options?: WorkerOptions) {
          super(url, options)
          this.addEventListener('message', ({ data }) => {
            if (data.type !== 'pose-result') return
            const video = document.querySelector('video')!
            frames.push({ timestampMs: video.currentTime * 1000, poses: data.poses,
              aspect: video.videoWidth / video.videoHeight * (crop ? (crop[2]-crop[0])/(crop[3]-crop[1]) : 1) })
          })
        }
      }
      if (crop) {
        const original = window.createImageBitmap.bind(window)
        window.createImageBitmap = ((source: ImageBitmapSource, options?: ImageBitmapOptions) => {
          if (source instanceof HTMLVideoElement) {
            const [x,y,right,bottom] = crop
            const width = Math.round((right-x)*source.videoWidth), height = Math.round((bottom-y)*source.videoHeight)
            const factor = Math.min(1,960/Math.max(width,height))
            return original(source, Math.round(x*source.videoWidth), Math.round(y*source.videoHeight), width, height,
              { ...options, resizeWidth: Math.round(width*factor), resizeHeight: Math.round(height*factor) })
          }
          return original(source, options)
        }) as typeof createImageBitmap
      }
    }, { crop: clip.crop })
    await page.goto('/lab')
    await expect(page.getByTestId('model-status')).toHaveText('Waiting for camera', { timeout: 45000 })
    await page.getByLabel('Open local video').setInputFiles(path)
    await expect(page.getByTestId('camera-status')).toHaveText('Review complete', { timeout: 360000 })
    const frames = await page.evaluate(() => (window as unknown as { __baselineFrames: Array<{ timestampMs: number; poses: PoseLandmarks[]; aspect: number }> }).__baselineFrames)
    const engine = new ConflictEngine()
    const events = new Map()
    for (const frame of frames) {
      const result = engine.update(frame.timestampMs, frame.poses, frame.aspect)
      result.events.forEach(event => events.set(event.id, event))
    }
    report.clips[clip.id] = { events: [...events.values()], frameCount: frames.length }
    await writeFile(resolve(dirname(manifest), 'runs/baseline.json'), JSON.stringify(report,null,2))
    await page.getByTestId('stop-camera').click()
    await context.close()
  }
})

