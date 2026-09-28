import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test.use({ video: 'off', trace: 'off' })
test('real local AI stream, camera lifecycle, partial view, responsive UI and connection loss', async ({ page }) => {
  test.skip(process.env.NIVRA_LOCAL_AI !== '1', 'Start the local AI service on port 8765 first')
  test.setTimeout(180000)
  const errors: string[] = []
  const consoleErrors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  await page.route('**/__local_fixture.webm', route => route.fulfill({ path: resolve('service/evaluation/media/grappling.webm'), contentType: 'video/webm' }))
  await page.addInitScript(() => {
    const proof = { frames: 0, latency: [] as number[], tracked: 0, crop: false }
    Object.assign(window, { __localProof: proof })
    const NativeSocket = window.WebSocket
    window.WebSocket = class extends NativeSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols)
        this.addEventListener('message', ({ data }) => {
          const result = JSON.parse(data)
          proof.frames++
          proof.tracked = result.tracks.length
          proof.latency.push(performance.now() - result.timestampMs)
        })
      }
    }
    navigator.mediaDevices.getUserMedia = async () => {
      const video = document.createElement('video'); video.src = '/__local_fixture.webm'; video.loop = true; video.muted = true
      await video.play()
      const canvas = document.createElement('canvas'); canvas.width=640;canvas.height=440
      const context=canvas.getContext('2d')!
      const draw=()=>context.drawImage(video,0,0,video.videoWidth,video.videoHeight*(proof.crop?.7:1),0,0,640,440)
      draw();const timer=setInterval(draw,66)
      const stream=canvas.captureStream(15);const track=stream.getVideoTracks()[0];const stop=track.stop.bind(track)
      track.stop=()=>{clearInterval(timer);video.pause();video.removeAttribute('src');video.load();stop()}
      return stream
    }
  })
  await page.goto('http://127.0.0.1:8765/lab')
  await expect(page.getByTestId('model-status')).toHaveText('Waiting for camera',{timeout:45000})
  await page.getByTestId('start-camera').click()
  await expect(page.getByTestId('camera-status')).toHaveText('Camera live')
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {__localProof:{frames:number}}).__localProof.frames),{timeout:30000}).toBeGreaterThan(20)
  await expect(page.getByTestId('coverage-detected')).not.toHaveText('0')
  await page.screenshot({path:'test-results/local-ai-desktop.png',fullPage:true})
  await page.evaluate(() => { (window as unknown as {__localProof:{crop:boolean}}).__localProof.crop=true })
  await expect.poll(()=>page.evaluate(()=>(window as unknown as {__localProof:{frames:number}}).__localProof.frames),{timeout:30000}).toBeGreaterThan(45)
  await page.getByTestId('stop-camera').click()
  await expect(page.getByTestId('camera-status')).toHaveText('Camera ready')
  await page.getByTestId('start-camera').click()
  await expect(page.getByTestId('camera-status')).toHaveText('Camera live')
  await page.setViewportSize({width:390,height:844})
  await page.getByText('Detection settings',{exact:true}).click()
  await expect(page.getByLabel('Analysis engine',{exact:false})).toHaveValue('local-ai')
  if (process.env.NIVRA_CLASSROOM_AI === '1') {
    await expect(page.getByLabel('People limit',{exact:false})).toHaveValue('50')
    await expect(page.getByText('Classroom AI candidate · RTMO + SlowFast + X3D.',{exact:false})).toBeVisible()
  }
  await expect(page.getByLabel('Pose model',{exact:true})).toBeDisabled()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true)
  await page.screenshot({path:'test-results/local-ai-mobile.png',fullPage:true})
  await page.getByTestId('stop-camera').click()
  const metrics=await page.evaluate(()=>(window as unknown as {__localProof:{frames:number;latency:number[]}}).__localProof)
  await test.info().attach('real-camera-pipeline-proof',{body:JSON.stringify(metrics),contentType:'application/json'})
  expect(consoleErrors).toEqual([])
  // Block only the bootstrap endpoint, then verify explicit error/recovery UI.
  await page.route('**/api/v1/session', route=>route.fulfill({status:503,body:'Unavailable'}))
  await page.getByLabel('Analysis engine',{exact:false}).focus()
  await expect(page.getByLabel('Analysis engine',{exact:false})).toBeFocused()
  await page.getByLabel('Analysis engine',{exact:false}).press('Home')
  await expect(page.getByLabel('Analysis engine',{exact:false})).toHaveValue('browser')
  await page.getByLabel('Analysis engine',{exact:false}).selectOption('local-ai')
  await expect(page.getByRole('button',{name:'Retry analysis',exact:true})).toBeVisible()
  await expect(page.getByLabel('Analysis engine',{exact:false})).toHaveValue('local-ai')
  expect(errors).toEqual([])
})

