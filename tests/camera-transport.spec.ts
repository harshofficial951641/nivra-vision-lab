import { expect, test } from '@playwright/test'

test.use({ video: 'off', trace: 'off' })

test('phone sends smoothly with delayed acknowledgements, stops, reconnects and reports failure', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error' && message.text() !== 'INFO: Created TensorFlow Lite XNNPACK delegate for CPU.') errors.push(message.text())
  })
  await page.route('**/api/v2/camera/session', (route) => route.fulfill({
    json: { id: 'qa', name: 'Transport QA', building: 'Test', floor: '1' },
  }))
  let received = 0
  let deviceResults = 0
  const timers = new Set<ReturnType<typeof setTimeout>>()
  let fail = () => {}
  await page.routeWebSocket('**/api/v2/camera/stream', (socket) => {
    const ready = setTimeout(() => socket.send(JSON.stringify({ type: 'ready', maxFps: 12 })), 20)
    timers.add(ready)
    fail = () => socket.close({ code: 1013, reason: 'Service unavailable' })
    socket.onMessage((message) => {
      if (typeof message === 'string') {
        if (JSON.parse(message).type === 'device-result') deviceResults++
        return
      }
      const packet = Buffer.from(message)
      const size = packet.readUInt32LE(0)
      const header = JSON.parse(packet.subarray(4, 4 + size).toString())
      received++
      const timer = setTimeout(() => {
        socket.send(JSON.stringify({ type: 'accepted', timestampMs: header.timestampMs }))
        timers.delete(timer)
      }, 400)
      timers.add(timer)
    })
    socket.onClose(() => {
      timers.forEach(clearTimeout)
      timers.clear()
    })
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/camera')
  await expect(page.getByRole('heading', { name: 'Transport QA' })).toBeVisible()
  await page.getByLabel('Analyze area', { exact: true }).selectOption('center')
  await expect(page.getByText('Analyzed area only', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Processing', { exact: true })).toHaveValue('balanced')
  await page.getByRole('button', { name: 'Start camera' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByText('Sending live frames', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Analyze area', { exact: true })).toBeDisabled()
  // A stop-and-wait sender can manage at most ~12 frames in five seconds here.
  await expect.poll(() => received, { timeout: 5000 }).toBeGreaterThan(35)
  await expect.poll(() => deviceResults, { timeout: 20000 }).toBeGreaterThan(2)
  await expect(page.getByText(/Device (GPU|CPU fallback) ·/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/transport-publisher-mobile.png', fullPage: true })
  await page.getByRole('button', { name: 'Stop camera' }).click()
  const stoppedAt = received
  await expect(page.locator('video')).toHaveJSProperty('srcObject', null)
  await page.getByLabel('Analyze area', { exact: true }).selectOption('full')
  await expect(page.getByText('Analyzed area only', { exact: true })).toHaveCount(0)
  await page.waitForTimeout(500)
  expect(received).toBe(stoppedAt)
  await page.getByRole('button', { name: 'Reconnect camera' }).click()
  await expect.poll(() => received).toBeGreaterThan(stoppedAt + 5)
  fail()
  await expect(page.getByRole('alert')).toContainText('Connection ended')
  await expect(page.locator('video')).toHaveJSProperty('srcObject', null)
  expect(errors).toEqual([])
})
