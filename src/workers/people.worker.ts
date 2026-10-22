/// <reference lib="webworker" />
import { FilesetResolver, ObjectDetector } from '@mediapipe/tasks-vision'
import { DEVICE_PEOPLE_LIMIT } from '../classroom/capacity'
import { personDetections } from '../classroom/personDetections'
import type { PeopleWorkerRequest, PeopleWorkerResponse } from '../classroom/peopleContracts'

const scope = self as unknown as DedicatedWorkerGlobalScope
let detector: ObjectDetector | null = null
let operation = Promise.resolve()
const respond = (message: PeopleWorkerResponse) => scope.postMessage(message)
async function handle(message: PeopleWorkerRequest) {
  if (message.type === 'init') {
    const response = await fetch(message.modelPath)
    if (!response.ok) throw new Error(`Person model could not load (${response.status}).`)
    const bytes = new Uint8Array(await response.arrayBuffer())
    const fileset = await FilesetResolver.forVisionTasks(message.wasmRoot, true)
    detector = await ObjectDetector.createFromOptions(fileset, {
      baseOptions: { modelAssetBuffer: bytes, delegate: 'CPU' },
      runningMode: 'VIDEO', maxResults: DEVICE_PEOPLE_LIMIT,
      categoryAllowlist: ['person'], scoreThreshold: .25,
    })
    respond({ type: 'ready' })
    return
  }
  try {
    if (!detector) throw new Error('Person detector is not ready.')
    const started = performance.now()
    const output = detector.detectForVideo(message.bitmap, message.timestampMs)
    const people = personDetections(output.detections, message.bitmap.width, message.bitmap.height)
    respond({ type: 'people-result', result: { timestampMs: message.timestampMs, inferenceMs: performance.now() - started, people } })
  } finally { message.bitmap.close() }
}
scope.onmessage = ({ data }: MessageEvent<PeopleWorkerRequest>) => {
  operation = operation.then(() => handle(data)).catch(reason => {
    respond({ type: 'error', message: reason instanceof Error ? reason.message : 'Person detection failed.' })
  })
}
