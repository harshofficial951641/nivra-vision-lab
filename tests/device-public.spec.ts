import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { expect, test } from '@playwright/test'

test.use({ trace: 'off', video: 'off' })

test('real browser model reports through the public relay without PC inference', async ({ page, context, playwright }) => {
  test.skip(process.env.NIVRA_DEVICE_PUBLIC !== '1', 'Explicit opt-in: creates and removes its own temporary public QA camera')
  test.setTimeout(90000)
  const publicOrigin = 'https://nivra-vision-lab.topperly.chatgpt.site'
  const local = await playwright.request.newContext({ baseURL: 'http://127.0.0.1:8765', extraHTTPHeaders: { Origin: 'http://127.0.0.1:8765' } })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => {
    if (message.type() === 'error' && message.text() !== 'INFO: Created TensorFlow Lite XNNPACK delegate for CPU.') errors.push(message.text())
  })
  expect((await local.post('/api/v2/session')).status()).toBe(204)
  const before = await (await local.get('/api/v2/state')).json()
  expect(before.runtime.compute).toBe('camera-device')
  const name = `Device QA ${Date.now()}`
  const created = await local.post('/api/v2/cameras', { data: { name, building: 'Synthetic QA', floor: 'Temporary' } })
  expect(created.status()).toBe(201)
  const camera = await created.json()
  try {
    const { url: operatorLink } = await (await local.post('/api/v2/operator/invite')).json()
    const token = new URLSearchParams(new URL(operatorLink).hash.slice(1)).get('operator')
    expect((await context.request.post(`${publicOrigin}/api/v2/operator/redeem`, { headers: { Origin: publicOrigin }, data: { token } })).status()).toBe(204)
    const { url } = await (await local.post(`/api/v2/cameras/${camera.id}/pair`)).json()
    await page.goto(url)
    await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Start camera', exact: true }).click()
    await expect(page.getByText(/Device (GPU|CPU fallback) ·/)).toBeVisible({ timeout: 45000 })
    await expect.poll(async () => {
      const state = await (await local.get('/api/v2/state')).json()
      return state.cameras.find((c: { id: string }) => c.id === camera.id)?.framesAnalyzed
    }, { timeout: 20000 }).toBeGreaterThan(3)
    const dashboard = await context.newPage()
    await dashboard.goto(publicOrigin)
    const card = dashboard.getByRole('article', { name, exact: true })
    await expect(card.getByRole('img', { name: `Live view of ${name}` })).toBeVisible()
    await expect(card.getByText('Limited coverage', { exact: true })).toBeVisible()
    await expect(card.getByText(/Device (GPU|CPU) · up to 10 pose candidates/)).toBeVisible()
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: 'test-results/device-public-mobile.png', fullPage: true })
    await page.getByRole('button', { name: 'Stop camera', exact: true }).click()
    await expect(card.getByText('Camera offline', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Reconnect camera', exact: true }).click()
    await expect(card.getByText('Limited coverage', { exact: true })).toBeVisible({ timeout: 45000 })
    await page.getByRole('button', { name: 'Stop camera', exact: true }).click()
    await dashboard.close()
    expect(errors).toEqual([])
  } finally {
    await page.close()
    await local.patch(`/api/v2/cameras/${camera.id}`, { data: { name, building: 'Synthetic QA', floor: 'Temporary', enabled: false } })
    // Remove only this test's metadata row. Never delete or modify real camera events.
    execFileSync(resolve('service/.venv/Scripts/python.exe'), ['-c',
      'import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); assert d.execute("SELECT COUNT(*) FROM events WHERE camera_id=?",(sys.argv[2],)).fetchone()[0]==0; d.execute("DELETE FROM cameras WHERE id=? AND name=?",(sys.argv[2],sys.argv[3])); d.commit(); d.close()',
      resolve('service/state/classrooms.sqlite'), camera.id, name])
    await context.request.post(`${publicOrigin}/api/v2/operator/logout`, { headers: { Origin: publicOrigin } })
    await local.dispose()
  }
})
