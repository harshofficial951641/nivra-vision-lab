import { expect, test } from '@playwright/test'
test.use({ video: 'off', trace: 'off' })

test('sample camera wall: review, filters, keyboard, responsive states and no recording controls', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await page.setViewportSize({ width: 1586, height: 992 })
  await page.goto('/?demo=1')
  await expect(
    page.getByRole('heading', { name: 'Live view', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText(
      'Generated imagery & illustrative events. No live detection.',
    ),
  ).toBeVisible()
  await expect(page.locator('.nv-camera-card')).toHaveCount(4)
  await page.screenshot({
    path: 'test-results/classroom-desktop.png',
    fullPage: true,
  })
  await page.getByLabel('Search cameras').fill('9A')
  await expect(page.locator('.nv-camera-card')).toHaveCount(1)
  await page.getByLabel('Search cameras').fill('')
  await page
    .getByLabel('Filter locations')
    .selectOption('Main building / Floor 1')
  await expect(page.locator('.nv-camera-card')).toHaveCount(2)
  await page.getByLabel('Filter locations').selectOption('all')
  await page.getByRole('button', { name: 'Focus', exact: true }).click()
  await expect(
    page.getByRole('button', { name: 'Focus', exact: true }),
  ).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '2 × 2', exact: true }).click()
  await page.getByRole('button', { name: 'Acknowledge', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'No pending reviews' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Mark resolved' }).click()
  await page.getByRole('button', { name: 'Analytics', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Current camera coverage' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await page.getByLabel('Visible person tracks').uncheck()
  await expect(page.getByLabel('Visible person tracks')).not.toBeChecked()
  await page.getByRole('button', { name: 'Live', exact: true }).click()
  await page
    .getByRole('button', { name: 'Details', exact: true })
    .first()
    .click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({
    path: 'test-results/classroom-mobile.png',
    fullPage: true,
  })
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await page.getByRole('button', { name: 'Cameras', exact: true }).click()
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click()
  await expect(page.getByLabel('Classroom name')).toBeFocused()
  await page.screenshot({
    path: 'test-results/classroom-mobile-dialog.png',
    fullPage: true,
  })
  await page.keyboard.press('Escape')
  expect(errors).toEqual([])
})

test('real service: pair camera, stream, stop, restart, revoke and disconnect', async ({
  page,
  context,
}) => {
  test.skip(
    process.env.NIVRA_CLASSROOM_AI !== '1',
    'Requires classroom service with a disposable metadata database on 8765',
  )
  test.setTimeout(120000)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('http://127.0.0.1:8765/')
  await expect(
    page.getByRole('button', { name: 'Add camera', exact: true }),
  ).toBeEnabled({ timeout: 30000 })
  await page.getByRole('button', { name: 'Add camera', exact: true }).click()
  const room = `QA ${Date.now()}`
  await page.getByLabel('Classroom name').fill(room)
  await page.getByRole('button', { name: 'Save location', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  const card = page.getByRole('article', { name: room, exact: true })
  await card.getByRole('button', { name: 'Connect device' }).click()
  await expect(
    page.getByText('This link works on this computer only.', { exact: false }),
  ).toBeVisible()
  const link = await page.getByLabel('Pairing link').inputValue()
  const publisher = await context.newPage()
  publisher.on('pageerror', (error) => errors.push(error.message))
  await publisher.goto(link)
  await expect(
    publisher.getByRole('heading', { name: room, exact: true }),
  ).toBeVisible()
  await publisher
    .getByRole('button', { name: 'Start camera', exact: true })
    .click()
  await expect(
    publisher.getByText('Sending live frames', { exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await expect(
    card.getByRole('img', { name: `Live view of ${room}` }),
  ).toBeVisible({ timeout: 20000 })
  await expect(
    card
      .getByText('Analysis current', { exact: true })
      .or(card.getByText('Limited coverage', { exact: true })),
  ).toBeVisible({ timeout: 30000 })
  await page.screenshot({
    path: 'test-results/classroom-live-source.png',
    fullPage: true,
  })
  await publisher.setViewportSize({ width: 390, height: 844 })
  await publisher.screenshot({
    path: 'test-results/classroom-publisher-mobile.png',
    fullPage: true,
  })
  expect(
    await publisher.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true)
  await publisher
    .getByRole('button', { name: 'Stop camera', exact: true })
    .click()
  await expect(card.getByText('Camera offline', { exact: true })).toBeVisible({
    timeout: 10000,
  })
  await publisher
    .getByRole('button', { name: 'Reconnect camera', exact: true })
    .click()
  await expect(
    card.getByRole('img', { name: `Live view of ${room}` }),
  ).toBeVisible({ timeout: 20000 })
  await card.getByRole('button', { name: 'Details', exact: true }).click()
  await page.getByRole('button', { name: 'Pause camera', exact: true }).click()
  await expect(
    publisher.getByText('Connection ended.', { exact: false }),
  ).toBeVisible({ timeout: 10000 })
  await expect(card.getByText('Camera paused', { exact: true })).toBeVisible()
  await publisher.close()
  // Only block the service handshake; UI must not retain a healthy/live status.
  await page.route('**/api/v2/session', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Service unavailable' }),
    }),
  )
  await page.reload()
  await expect(page.getByRole('alert')).toContainText(
    'Feeds and analysis are unavailable',
  )
  await expect(
    page.getByRole('button', { name: 'Add camera', exact: true }),
  ).toBeDisabled()
  await page.screenshot({
    path: 'test-results/classroom-service-failure.png',
    fullPage: true,
  })
  expect(errors).toEqual([])
})
