/// <reference lib="webworker" />

import {
  FilesetResolver,
  ObjectDetector,
  PoseLandmarker,
} from '@mediapipe/tasks-vision'
import {
  DETECTOR_ALLOWLIST,
  isSupportedObjectLabel,
  objectDisplayName,
  objectRole,
} from '../lib/objectCatalog'
import { expandedPersonRegion, matchesPersonRegion, remapPersonPose } from './personPoses'
import { PORTRAIT_POSE_REGIONS, mergeCropPoses, ownsPortraitPose, remapCropPose } from './portraitPoses'
import { isSoftwareWebGlRenderer } from '../lib/gpuDelegate'
import type {
  ObjectObservation,
  PoseLandmarks,
  VisionDelegate,
  VisionTaskKind,
  VisionWorkerRequest,
  VisionWorkerResponse,
} from '../types/vision'

const workerScope = self as unknown as DedicatedWorkerGlobalScope

let task: VisionTaskKind | null = null
let poseLandmarker: PoseLandmarker | null = null
let objectDetector: ObjectDetector | null = null
let delegate: VisionDelegate = 'CPU'
let operation = Promise.resolve()
let portraitMultiPerson = false
let poseMode: 'VIDEO' | 'IMAGE' = 'VIDEO'
let maxPoses = 10
let cropCanvas: OffscreenCanvas | null = null

function respond(message: VisionWorkerResponse): void {
  workerScope.postMessage(message)
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown vision-processing error.'
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function toPlainPoses(poses: PoseLandmarks[]): PoseLandmarks[] {
  return poses.map((pose) =>
    pose.map((landmark) => ({
      x: landmark.x,
      y: landmark.y,
      z: landmark.z,
      visibility: landmark.visibility,
      presence: landmark.presence,
    })),
  )
}

function toPlainObjects(
  result: ReturnType<ObjectDetector['detectForVideo']>,
  sourceWidth: number,
  sourceHeight: number,
): ObjectObservation[] {
  return result.detections.flatMap((detection) => {
    const category = detection.categories[0]
    const box = detection.boundingBox
    if (!category || !box || !isSupportedObjectLabel(category.categoryName)) return []
    const left = clamp(box.originX / sourceWidth)
    const top = clamp(box.originY / sourceHeight)
    const right = clamp((box.originX + box.width) / sourceWidth)
    const bottom = clamp((box.originY + box.height) / sourceHeight)
    if (right <= left || bottom <= top) return []
    return [{
      label: category.categoryName,
      displayName: objectDisplayName(category.categoryName),
      score: category.score,
      role: objectRole(category.categoryName),
      box: {
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      },
    }]
  })
}

async function fetchModel(path: string): Promise<Uint8Array> {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`Local model load failed (${response.status}).`)
  return new Uint8Array(await response.arrayBuffer())
}

async function createPoseTask(
  modelBytes: Uint8Array,
  wasmRoot: string,
  maxPoses: number,
  confidence: number,
  preferredDelegate: VisionDelegate,
): Promise<void> {
  const sharedOptions = {
    runningMode: 'VIDEO' as const,
    numPoses: maxPoses,
    minPoseDetectionConfidence: confidence,
    minPosePresenceConfidence: confidence,
    minTrackingConfidence: confidence,
    outputSegmentationMasks: false,
  }
  const createForDelegate = async (nextDelegate: VisionDelegate) => {
    // Each worker owns one MediaPipe task and one module-aware WASM runtime.
    const fileset = await FilesetResolver.forVisionTasks(wasmRoot, true)
    return PoseLandmarker.createFromOptions(fileset, {
      ...sharedOptions,
      baseOptions: { modelAssetBuffer: modelBytes.slice(), delegate: nextDelegate },
    })
  }
  if (preferredDelegate === 'CPU' || isSoftwareWebGlRenderer()) {
    poseLandmarker = await createForDelegate('CPU')
    delegate = 'CPU'
    return
  }
  try {
    poseLandmarker = await createForDelegate('GPU')
    delegate = 'GPU'
  } catch {
    poseLandmarker = await createForDelegate('CPU')
    delegate = 'CPU'
  }
}

async function createObjectTask(
  modelBytes: Uint8Array,
  wasmRoot: string,
  confidence: number,
): Promise<void> {
  const sharedOptions = {
    runningMode: 'VIDEO' as const,
    maxResults: 24,
    scoreThreshold: confidence,
    categoryAllowlist: [...DETECTOR_ALLOWLIST],
  }
  // Reserve WebGL for the high-frequency pose overlay. Running two MediaPipe
  // GPU graphs in parallel causes severe context contention in Chromium;
  // EfficientDet runs independently at a lower cadence on WASM CPU instead.
  const fileset = await FilesetResolver.forVisionTasks(wasmRoot, true)
  objectDetector = await ObjectDetector.createFromOptions(fileset, {
    ...sharedOptions,
    baseOptions: { modelAssetBuffer: modelBytes.slice(), delegate: 'CPU' },
  })
  delegate = 'CPU'
}

async function initialize(message: Extract<VisionWorkerRequest, { type: 'init' }>) {
  task = message.task
  portraitMultiPerson = message.portraitMultiPerson === true
  maxPoses = message.maxPoses
  poseMode = 'VIDEO'
  const model = await fetchModel(message.modelPath)
  if (task === 'pose') {
    await createPoseTask(
      model,
      message.wasmRoot,
      message.personProposalPose ? 1 : message.maxPoses,
      message.poseConfidence,
      message.poseDelegate ?? 'GPU',
    )
  } else {
    await createObjectTask(model, message.wasmRoot, message.objectConfidence)
  }
  respond({ type: 'ready', task, delegate })
}

async function handleMessage(message: VisionWorkerRequest): Promise<void> {
  if (message.type === 'init') {
    try {
      await initialize(message)
    } catch (error) {
      respond({ type: 'error', task: message.task, code: 'model-init', message: errorMessage(error) })
    }
    return
  }

  if (message.type === 'frame') {
    const startedAt = performance.now()
    try {
      if (task === 'pose' && poseLandmarker) {
        const portrait = portraitMultiPerson && message.bitmap.width / message.bitmap.height < .85
        const mode = message.personRegions !== undefined || portrait ? 'IMAGE' : 'VIDEO'
        if (poseMode !== mode) {
          await poseLandmarker.setOptions({ runningMode: mode })
          poseMode = mode
        }
        let poses: PoseLandmarks[]
        if (message.personRegions !== undefined) {
          poses = []
          for (const box of message.personRegions.slice(0, maxPoses)) {
            const region = expandedPersonRegion(box)
            const width = Math.max(1, Math.round((region[2] - region[0]) * message.bitmap.width))
            const height = Math.max(1, Math.round((region[3] - region[1]) * message.bitmap.height))
            if (!cropCanvas) cropCanvas = new OffscreenCanvas(width, height)
            cropCanvas.width = width; cropCanvas.height = height
            const context = cropCanvas.getContext('2d')
            if (!context) throw new Error('Person analysis canvas unavailable.')
            context.drawImage(message.bitmap, region[0] * message.bitmap.width, region[1] * message.bitmap.height, width, height, 0, 0, width, height)
            const candidates = toPlainPoses(poseLandmarker.detect(cropCanvas).landmarks)
              .map(pose => remapPersonPose(pose, region)).filter(pose => matchesPersonRegion(pose, box))
            if (candidates[0]) poses.push(candidates[0])
          }
        } else if (portrait) {
          const groups: PoseLandmarks[][] = []
          const width = Math.max(1, Math.round(message.bitmap.width * .65))
          if (!cropCanvas) cropCanvas = new OffscreenCanvas(width, message.bitmap.height)
          cropCanvas.width = width
          cropCanvas.height = message.bitmap.height
          const context = cropCanvas.getContext('2d')
          if (!context) throw new Error('Portrait analysis canvas unavailable.')
          for (const [tile, region] of PORTRAIT_POSE_REGIONS.entries()) {
            context.drawImage(message.bitmap, message.bitmap.width * region.x, 0, message.bitmap.width * region.width, message.bitmap.height, 0, 0, width, message.bitmap.height)
            const result = poseLandmarker.detect(cropCanvas)
            groups.push(toPlainPoses(result.landmarks).map(pose => remapCropPose(pose, region)).filter(pose => ownsPortraitPose(pose, tile)))
          }
          poses = mergeCropPoses(groups, message.bitmap.width / message.bitmap.height, maxPoses)
        } else poses = toPlainPoses(poseLandmarker.detectForVideo(message.bitmap, message.timestampMs).landmarks)
        respond({
          type: 'pose-result',
          timestampMs: message.timestampMs,
          // Include both portrait passes and mode changes in pacing feedback.
          inferenceMs: performance.now() - startedAt,
          poses,
        })
      } else if (task === 'objects' && objectDetector) {
        const result = objectDetector.detectForVideo(message.bitmap, message.timestampMs)
        respond({
          type: 'object-result',
          timestampMs: message.timestampMs,
          inferenceMs: performance.now() - startedAt,
          objects: toPlainObjects(result, message.bitmap.width, message.bitmap.height),
        })
      } else {
        throw new Error('The local vision model is not ready yet.')
      }
    } catch (error) {
      respond({ type: 'error', task, code: 'inference', message: errorMessage(error) })
    } finally {
      message.bitmap.close()
    }
    return
  }

  if (message.type === 'configure') {
    try {
      if (task === 'pose') {
        maxPoses = message.maxPoses
        await poseLandmarker?.setOptions({
          numPoses: message.maxPoses,
          minPoseDetectionConfidence: message.poseConfidence,
          minPosePresenceConfidence: message.poseConfidence,
          minTrackingConfidence: message.poseConfidence,
        })
      } else {
        await objectDetector?.setOptions({ scoreThreshold: message.objectConfidence })
      }
    } catch (error) {
      respond({ type: 'error', task, code: 'model-config', message: errorMessage(error) })
    }
    return
  }

  poseLandmarker?.close()
  objectDetector?.close()
  poseLandmarker = null
  objectDetector = null
  cropCanvas = null
  workerScope.close()
}

workerScope.onmessage = (event: MessageEvent<VisionWorkerRequest>) => {
  operation = operation.then(() => handleMessage(event.data)).catch((error) => {
    // Keep a rejected operation from silently blocking every later message.
    respond({ type: 'error', task, code: 'worker-operation', message: errorMessage(error) })
  })
}
