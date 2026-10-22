import {chromium} from 'playwright'
import fs from 'node:fs/promises'
const browser = await chromium.launch({headless:true,args:['--disable-gpu']})
try {
  const context = await browser.newContext()
  await context.route('**/*',route => {
    const url = new URL(route.request().url())
    return ['127.0.0.1','localhost'].includes(url.hostname) ? route.continue() : route.abort()
  })
  const page = await context.newPage()
  page.on('pageerror',error => console.error('Harness error:',error.message))
  await page.goto('http://127.0.0.1:5188/test-results/original-pose-fresh/',{waitUntil:'domcontentloaded'})
  await page.waitForFunction(() => window.__poseReplay?.done || window.__poseReplay?.error,null,{timeout:240000})
  const data = await page.evaluate(() => window.__poseReplay)
  if(data.error) throw new Error(data.error)
  await fs.writeFile('test-results/original-pose-fresh/results.private.json',JSON.stringify(data,null,2))
  console.log(JSON.stringify({done:data.done,runs:data.runs.map(run=>({clip:run.clip,delegate:run.delegate,frames:run.rows.length}))}))
} finally {await browser.close()}
