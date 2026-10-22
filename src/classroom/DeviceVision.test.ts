import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DeviceVision } from './DeviceVision'
import { demoFrame } from '../lib/demoScene'

class WorkerStub {
  static all: WorkerStub[] = []
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  postMessage = vi.fn()
  terminate = vi.fn()
  constructor() { WorkerStub.all.push(this) }
  emit(data: unknown) { this.onmessage?.({ data }) }
}
const video = { readyState: 4, videoWidth: 1280, videoHeight: 720 } as HTMLVideoElement
const bitmap = () => ({ width: 1280, height: 720, close: vi.fn() })
const ready = async (delegate = 'GPU', offset = 0) => {
  WorkerStub.all[offset].emit({ type: 'ready', task: 'pose', delegate })
  WorkerStub.all[offset + 1].emit({ type: 'ready' })
  await Promise.resolve()
}
const people = async (timestampMs: number, inferenceMs = 20, boxes: { box: number[]; score: number }[] = [], offset = 0) => {
  WorkerStub.all[offset + 1].emit({ type: 'people-result', result: { timestampMs, inferenceMs, people: boxes } })
  await Promise.resolve()
}
beforeEach(() => { vi.useFakeTimers(); WorkerStub.all = []; vi.stubGlobal('Worker', WorkerStub) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('combined device worker lifecycle', () => {
  it('uses fresh pose pixels between detector refreshes without adding inference latency pacing', async () => {
    const source = bitmap()
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(source))
    const device = new DeviceVision(vi.fn(), vi.fn(), 'right', 'balanced')
    device.start()
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledWith(expect.objectContaining({ portraitMultiPerson: false }))
    await ready('CPU')
    await device.capture(video, 100)
    expect(createImageBitmap).toHaveBeenNthCalledWith(1, video, expect.objectContaining({ resizeWidth: 1280, resizeHeight: 720 }))
    expect(createImageBitmap).toHaveBeenNthCalledWith(2, source, 640, 0, 640, 720, expect.objectContaining({ resizeHeight: 720 }))
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(1)
    await people(100)
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 300 })
    await device.capture(video, 400)
    expect(createImageBitmap).toHaveBeenCalledTimes(4)
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledTimes(2) // init + initial detector frame
    expect(WorkerStub.all[0].postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 400, personRegions: [] }), expect.any(Array))
    await device.capture(video, 500)
    expect(createImageBitmap).toHaveBeenCalledTimes(4) // no queue while pose is busy
    expect(device.budget.previewSide).toBe(640)
    device.dispose()
  })
  it('uses up to32 person proposals with one-person pose inference and matching source timestamps', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap()))
    const status = vi.fn(), result = vi.fn(), device = new DeviceVision(status, result)
    device.start()
    const worker = WorkerStub.all[0]
    expect(worker.postMessage).toHaveBeenCalledWith(expect.objectContaining({ task: 'pose', poseDelegate: 'GPU', maxPoses: 32, personProposalPose: true }))
    worker.emit({ type: 'ready', delegate: 'GPU' })
    await device.capture(video, 50)
    expect(createImageBitmap).not.toHaveBeenCalled()
    WorkerStub.all[1].emit({ type: 'ready' }); await Promise.resolve()
    await device.capture(video, 100)
    await device.capture(video, 250)
    expect(createImageBitmap).toHaveBeenCalledTimes(2)
    expect(worker.postMessage).toHaveBeenCalledTimes(1)
    await people(100, 800, [{ box: [.1, .1, .2, .5], score: .9 }, { box: [.6, .1, .8, .9], score: .8 }])
    expect(worker.postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'frame', timestampMs: 100, personRegions: [[.1, .1, .2, .5], [.6, .1, .8, .9]] }), expect.any(Array))
    expect(result).not.toHaveBeenCalled()
    worker.emit({ type: 'pose-result', timestampMs: 99, poses: [], inferenceMs: 12 })
    expect(result).not.toHaveBeenCalled()
    worker.emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 12 })
    expect(result).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ timestampMs: 100, delegate: 'GPU', inferenceMs: 812, observedPeople: 2, usablePeople: 0 }))
    expect(device.budget.inferenceMs).toBe(812)
    device.dispose()
    expect(worker.terminate).toHaveBeenCalledOnce()
    expect(WorkerStub.all[1].terminate).toHaveBeenCalledOnce()
  })
  it('keeps sampling motion during a slow proposal refresh and never counts old boxes on a newer frame', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockImplementation(() => Promise.resolve(bitmap())))
    const result = vi.fn(), device = new DeviceVision(vi.fn(), result)
    device.start(); await ready()
    await device.capture(video, 100)
    await people(100, 100, [{ box: [.1, .1, .3, .8], score: .9 }])
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 50 })
    expect(result).toHaveBeenLastCalledWith(expect.objectContaining({ observedPeople: 1 }))
    await device.capture(video, 700)
    expect(WorkerStub.all[0].postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 700, personRegions: [[.1, .1, .3, .8]] }), expect.any(Array))
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 700, poses: [], inferenceMs: 50 })
    expect(result).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 700, observedPeople: 0, inferenceMs: 50 }))
    await device.capture(video, 800)
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledTimes(3) // no duplicate person job
    await people(700, 800, [{ box: [.5, .1, .8, .9], score: .9 }])
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 800, poses: [], inferenceMs: 50 })
    expect(result).toHaveBeenCalledTimes(3)
    expect(result).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 800, observedPeople: 0, inferenceMs: 50 }))
    await device.capture(video, 900)
    expect(WorkerStub.all[0].postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 900, personRegions: [[.5, .1, .8, .9]] }), expect.any(Array))
    device.dispose()
  })
  it('uses CPU fallback after a GPU stall and releases both crowd models and retries after a CPU stall', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap()))
    const status = vi.fn(), device = new DeviceVision(status, vi.fn())
    device.start()
    await ready()
    await device.capture(video, 100)
    await people(100)
    await vi.advanceTimersByTimeAsync(15001)
    expect(WorkerStub.all).toHaveLength(4)
    expect(WorkerStub.all[2].postMessage).toHaveBeenCalledWith(expect.objectContaining({ poseDelegate: 'CPU', maxPoses: 32, personProposalPose: true }))
    await ready('CPU', 2)
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'ready', delegate: 'CPU' }))
    await device.capture(video, 6000)
    await people(6000, 20, [], 2)
    await vi.advanceTimersByTimeAsync(30001)
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'loading', detail: 'Retrying detection (1/3)' }))
    expect(WorkerStub.all[2].terminate).toHaveBeenCalledOnce()
    expect(WorkerStub.all[3].terminate).toHaveBeenCalledOnce()
  })
  it('releases a captured bitmap if stopped before its crop is created', async () => {
    let resolve!: (value: unknown) => void
    vi.stubGlobal('createImageBitmap', vi.fn(() => new Promise(r => { resolve = r })))
    const device = new DeviceVision(vi.fn(), vi.fn())
    device.start()
    await ready()
    const capture = device.capture(video, 100)
    device.dispose()
    const source = bitmap(); resolve(source); await capture
    expect(source.close).toHaveBeenCalledOnce()
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(1)
  })
  it('does not publish pose-only results if person inference fails', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap()))
    const status = vi.fn(), result = vi.fn(), device = new DeviceVision(status, result)
    device.start(); await ready(); await device.capture(video, 100)
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 10 })
    WorkerStub.all[1].emit({ type: 'error', message: 'Person model unavailable' }); await Promise.resolve(); await Promise.resolve()
    expect(result).not.toHaveBeenCalled()
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'loading', detail: 'Retrying detection (1/3)' }))
  })
})

describe('independent original motion lane', () => {
  it('starts original full VIDEO tracking without waiting for crowd readiness, with only one GPU task', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockImplementation(() => Promise.resolve(bitmap())))
    const motion = vi.fn(), motionStatus = vi.fn(), crowd = vi.fn()
    const device = new DeviceVision(vi.fn(), crowd, 'right', 'balanced', motion, motionStatus)
    device.start('GPU')
    expect(WorkerStub.all).toHaveLength(3)
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledWith(expect.objectContaining({ modelPath: expect.stringContaining('pose_landmarker_full.task'), poseDelegate: 'GPU', maxPoses: 4, personProposalPose: false, portraitMultiPerson: false }))
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledWith(expect.objectContaining({ poseDelegate: 'CPU', personProposalPose: true }))
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    expect(motionStatus).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'ready', delegate: 'GPU' }))
    await device.capture(video, 100)
    await device.capture(video, 120)
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(2)
    expect(createImageBitmap).toHaveBeenCalledWith(video, 640, 0, 640, 720, expect.objectContaining({ resizeWidth: 640, resizeHeight: 720 }))
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 99, poses: [], inferenceMs: 80 })
    expect(motion).not.toHaveBeenCalled()
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 100, poses: [], inferenceMs: 80 })
    expect(motion).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ type: 'device-motion', timestampMs: 100, inferenceMs: 80 }))
    expect(crowd).not.toHaveBeenCalled()
    WorkerStub.all[1].emit({ type: 'error', message: 'Crowd failed' })
    await device.capture(video, 250)
    expect(WorkerStub.all[0].postMessage).toHaveBeenLastCalledWith(expect.objectContaining({ timestampMs: 250 }), expect.any(Array))
    device.dispose()
    expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
  })
  it('falls back motion independently and preserves the crowd lane when motion stalls', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockImplementation(() => Promise.resolve(bitmap())))
    const motionStatus = vi.fn(), crowdStatus = vi.fn()
    const device = new DeviceVision(crowdStatus, vi.fn(), 'full', 'balanced', vi.fn(), motionStatus)
    device.start('GPU')
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    await device.capture(video, 100)
    await vi.advanceTimersByTimeAsync(5001)
    expect(WorkerStub.all).toHaveLength(4)
    expect(WorkerStub.all[3].postMessage).toHaveBeenCalledWith(expect.objectContaining({ poseDelegate: 'CPU', maxPoses: 4 }))
    expect(WorkerStub.all[1].terminate).not.toHaveBeenCalled()
    WorkerStub.all[3].emit({ type: 'ready', delegate: 'CPU' })
    expect(motionStatus).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'ready', delegate: 'CPU' }))
    await device.capture(video, 6000)
    await vi.advanceTimersByTimeAsync(10001)
    expect(motionStatus).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'loading', detail: 'Retrying detection (1/3)' }))
    WorkerStub.all[1].emit({ type: 'ready', delegate: 'CPU' })
    WorkerStub.all[2].emit({ type: 'ready' }); await Promise.resolve()
    expect(crowdStatus).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'ready', delegate: 'CPU' }))
    await device.capture(video, 17000)
    expect(WorkerStub.all[2].postMessage).toHaveBeenCalledTimes(2)
    device.dispose()
  })
})

describe('bounded model recovery', () => {
  it('keeps GPU fallback separate and allows only three CPU retries despite repeated ready/error cycles', async () => {
    const status = vi.fn(), device = new DeviceVision(status, vi.fn())
    device.start('GPU')
    WorkerStub.all[0].emit({ type: 'error' })
    expect(WorkerStub.all).toHaveLength(4)
    const delays = [500, 1500, 3000]
    for (let attempt = 0; attempt <= 3; attempt++) {
      const offset = 2 + attempt * 2
      await ready('CPU', offset)
      WorkerStub.all[offset].emit({ type: 'error' })
      if (attempt < 3) {
        expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'loading', detail: `Retrying detection (${attempt + 1}/3)` }))
        await vi.advanceTimersByTimeAsync(delays[attempt] - 1)
        expect(WorkerStub.all).toHaveLength(offset + 2)
        await vi.advanceTimersByTimeAsync(1)
        expect(WorkerStub.all).toHaveLength(offset + 4)
      }
    }
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'error', detail: 'Detection unavailable. Retry detection.' }))
    await vi.advanceTimersByTimeAsync(10000)
    expect(WorkerStub.all).toHaveLength(10)
    device.start('CPU')
    await ready('CPU', 10)
    WorkerStub.all[10].emit({ type: 'error' })
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({ detail: 'Retrying detection (1/3)' }))
    device.dispose()
  })
  it('bounds original motion retries independently while healthy crowd workers keep running', async () => {
    const motionStatus = vi.fn(), device = new DeviceVision(vi.fn(), vi.fn(), 'full', 'balanced', vi.fn(), motionStatus)
    device.start('CPU')
    WorkerStub.all[1].emit({ type: 'ready', delegate: 'CPU' })
    WorkerStub.all[2].emit({ type: 'ready' }); await Promise.resolve()
    for (let attempt = 0; attempt <= 3; attempt++) {
      const index = attempt === 0 ? 0 : attempt + 2
      WorkerStub.all[index].emit({ type: 'ready', delegate: 'CPU' })
      WorkerStub.all[index].emit({ type: 'error' })
      if (attempt < 3) await vi.advanceTimersByTimeAsync([500, 1500, 3000][attempt])
    }
    expect(motionStatus).toHaveBeenLastCalledWith(expect.objectContaining({ state: 'error', detail: 'Motion unavailable. Retry detection.' }))
    expect(WorkerStub.all[1].terminate).not.toHaveBeenCalled()
    expect(WorkerStub.all[2].terminate).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(10000)
    expect(WorkerStub.all).toHaveLength(6)
    device.dispose()
  })
  it('retries a failed crowd model without reloading healthy original motion', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockImplementation(() => Promise.resolve(bitmap())))
    const motion = vi.fn(), motionStatus = vi.fn()
    const device = new DeviceVision(vi.fn(), vi.fn(), 'full', 'balanced', motion, motionStatus)
    device.start('CPU')
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'CPU' })
    WorkerStub.all[1].emit({ type: 'error' })
    await vi.advanceTimersByTimeAsync(500)
    expect(WorkerStub.all).toHaveLength(5)
    expect(WorkerStub.all[0].terminate).not.toHaveBeenCalled()
    expect(motionStatus).toHaveBeenCalledTimes(2) // initial loading and actual ready only
    await device.capture(video, 1000)
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 1000, poses: [], inferenceMs: 70 })
    expect(motion).toHaveBeenCalledWith(expect.objectContaining({ type: 'device-motion', timestampMs: 1000 }))
    device.dispose()
  })
  it('cancels both independent retry timers on Stop and ignores delayed worker messages', async () => {
    const status = vi.fn(), motionStatus = vi.fn()
    const device = new DeviceVision(status, vi.fn(), 'full', 'balanced', vi.fn(), motionStatus)
    device.start('CPU')
    WorkerStub.all[0].emit({ type: 'error' })
    WorkerStub.all[1].emit({ type: 'error' })
    device.dispose()
    const calls = status.mock.calls.length, motionCalls = motionStatus.mock.calls.length
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'CPU' })
    WorkerStub.all[1].emit({ type: 'ready', delegate: 'CPU' })
    await vi.advanceTimersByTimeAsync(10000)
    expect(WorkerStub.all).toHaveLength(3)
    expect(status).toHaveBeenCalledTimes(calls)
    expect(motionStatus).toHaveBeenCalledTimes(motionCalls)
  })
})


describe('published browser skeleton profile', () => {
  it('starts one Full VIDEO worker and emits the observed skeletons without waiting for another detector', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap()))
    const result = vi.fn(), status = vi.fn()
    const device = new DeviceVision(status, result, 'full', 'original')
    device.start()
    expect(WorkerStub.all).toHaveLength(1)
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledWith(expect.objectContaining({
      modelPath: expect.stringContaining('pose_landmarker_full.task'),
      maxPoses: 4, poseConfidence: .5, personProposalPose: false, portraitMultiPerson: false,
    }))
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    const source = { ...video, currentTime: 1 } as HTMLVideoElement
    await device.capture(source, 100)
    WorkerStub.all[0].emit({ type: 'pose-result', timestampMs: 100, poses: demoFrame(0, 'conflict').poses, inferenceMs: 20 })
    expect(result).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      type: 'device-result', observedPeople: 2, usablePeople: 2,
      poses: expect.arrayContaining([expect.arrayContaining([expect.any(Array)])]),
      events: [],
    }))
    expect(result.mock.calls[0][0].poses[0]).toHaveLength(33)
    await device.capture(source, 200)
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(2)
    source.currentTime = 2
    await device.capture(source, 300)
    expect(WorkerStub.all[0].postMessage).toHaveBeenCalledTimes(3)
    device.dispose()
    expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
  })

  it('falls back to one CPU worker when the original GPU pipeline stalls', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap()))
    const device = new DeviceVision(vi.fn(), vi.fn(), 'full', 'original')
    device.start()
    WorkerStub.all[0].emit({ type: 'ready', delegate: 'GPU' })
    await device.capture(video, 100)
    await vi.advanceTimersByTimeAsync(5001)
    expect(WorkerStub.all).toHaveLength(2)
    expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledWith(expect.objectContaining({ poseDelegate: 'CPU', maxPoses: 4, personProposalPose: false }))
    device.dispose()
  })
})

describe('guarded one-pass crowd profile',()=>{
  const model={modelPath:'/models/validated.onnx',sha256:'0'.repeat(64),inputSide:416 as const}
  it('uses only one graph and carries same-source32 boxes without serial person crops',async()=>{
    vi.stubGlobal('createImageBitmap',vi.fn().mockResolvedValue(bitmap()))
    const status=vi.fn(),result=vi.fn(),device=new DeviceVision(status,result,'full','crowd',undefined,undefined,model)
    device.start()
    expect(WorkerStub.all).toHaveLength(1)
    WorkerStub.all[0].emit({type:'ready'});await Promise.resolve()
    const capture = device.capture(video,100)
    await Promise.resolve()
    await device.capture(video,200)
    expect(createImageBitmap).toHaveBeenCalledOnce()
    const boxes=Array.from({length:32},(_,i)=>({box:[i/40,0,(i+1)/40,.5],score:.9}))
    WorkerStub.all[0].emit({type:'result',result:{timestampMs:100,inferenceMs:50,people:boxes,poses:[]}})
    await capture
    expect(result).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({timestampMs:100,delegate:'CPU',observedPeople:32,poses:[]}))
    expect(WorkerStub.all).toHaveLength(1)
    device.dispose();expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
  })
  it('stops an over-three-second crowd pass and loads one original Full fallback, with no late result',async()=>{
    vi.stubGlobal('createImageBitmap',vi.fn().mockResolvedValue(bitmap()))
    const status=vi.fn(),result=vi.fn(),device=new DeviceVision(status,result,'full','crowd',undefined,undefined,model)
    device.start();WorkerStub.all[0].emit({type:'ready'});await Promise.resolve()
    const first = device.capture(video,100)
    await Promise.resolve()
    WorkerStub.all[0].emit({type:'result',result:{timestampMs:100,inferenceMs:50,people:[],poses:[]}})
    await first
    const capture = device.capture(video,200)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(3000)
    await capture
    expect(WorkerStub.all[0].terminate).toHaveBeenCalledOnce()
    expect(WorkerStub.all).toHaveLength(2)
    expect(WorkerStub.all[1].postMessage).toHaveBeenCalledWith(expect.objectContaining({modelPath:expect.stringContaining('pose_landmarker_full'),maxPoses:4}))
    WorkerStub.all[0].emit({type:'result',result:{timestampMs:200,inferenceMs:50,people:[],poses:[]}})
    await Promise.resolve();expect(result).toHaveBeenCalledOnce()
    device.dispose();expect(WorkerStub.all[1].terminate).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('allows first-frame compilation while staying visibly loading, then bounds a permanent first stall',async()=>{
    vi.stubGlobal('createImageBitmap',vi.fn().mockResolvedValue(bitmap()))
    const status=vi.fn(),result=vi.fn(),device=new DeviceVision(status,result,'full','crowd',undefined,undefined,model)
    device.start();WorkerStub.all[0].emit({type:'ready',delegate:'CPU'});await Promise.resolve()
    const capture=device.capture(video,100)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(5500)
    expect(status).not.toHaveBeenCalledWith(expect.objectContaining({state:'ready'}))
    expect(WorkerStub.all).toHaveLength(1)
    WorkerStub.all[0].emit({type:'result',result:{timestampMs:100,inferenceMs:5500,delegate:'CPU',people:[],poses:[]}})
    await capture
    expect(status).toHaveBeenLastCalledWith(expect.objectContaining({state:'ready',delegate:'CPU'}))
    expect(result).toHaveBeenLastCalledWith(expect.objectContaining({conflict:expect.objectContaining({status:'limited',explanation:expect.stringContaining('600ms')})}))
    device.dispose()
    const stalled=new DeviceVision(vi.fn(),vi.fn(),'full','crowd',undefined,undefined,model)
    stalled.start();WorkerStub.all[1].emit({type:'ready'});await Promise.resolve()
    const first=stalled.capture(video,100)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(11999)
    expect(WorkerStub.all[1].terminate).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1);await first
    expect(WorkerStub.all[1].terminate).toHaveBeenCalledOnce()
    expect(WorkerStub.all).toHaveLength(3)
    stalled.dispose();expect(vi.getTimerCount()).toBe(0)
  })

})

describe('verified CPU crowd observation with original fast motion',()=>{
  it('keeps crowd reports observational and reuses the existing Full worker after crowd failure with the same event IDs',async()=>{
    vi.stubGlobal('createImageBitmap',vi.fn().mockImplementation(()=>Promise.resolve(bitmap())))
    const model={modelPath:'/models/validated.onnx',sha256:'0'.repeat(64),inputSide:416 as const,preferredDelegate:'CPU' as const}
    const status=vi.fn(),result=vi.fn(),motion=vi.fn(),motionStatus=vi.fn()
    const device=new DeviceVision(status,result,'full','crowd',motion,motionStatus,model)
    device.start()
    expect(WorkerStub.all).toHaveLength(2)
    const full=WorkerStub.all[0],crowd=WorkerStub.all[1]
    expect(full.postMessage).toHaveBeenCalledWith(expect.objectContaining({modelPath:expect.stringContaining('pose_landmarker_full'),poseDelegate:'GPU',maxPoses:4}))
    full.emit({type:'ready',delegate:'GPU'});crowd.emit({type:'ready',delegate:'CPU'});await Promise.resolve()
    const first=device.capture(video,100);await Promise.resolve()
    full.emit({type:'pose-result',timestampMs:100,inferenceMs:20,poses:[]})
    crowd.emit({type:'result',result:{timestampMs:100,inferenceMs:300,delegate:'CPU',people:[{box:[.1,.1,.3,.8],score:.9}],poses:[]}})
    await first
    expect(result).toHaveBeenLastCalledWith(expect.objectContaining({delegate:'CPU',observedPeople:1,usablePeople:0,events:[],conflict:expect.objectContaining({status:'limited',explanation:expect.stringContaining('Fast motion checks run separately')})}))
    expect(motion).toHaveBeenCalledOnce()
    const second=device.capture(video,200);await Promise.resolve()
    await vi.advanceTimersByTimeAsync(3000);await second
    expect(crowd.terminate).toHaveBeenCalledOnce()
    expect(full.terminate).not.toHaveBeenCalled()
    expect(WorkerStub.all).toHaveLength(2)
    full.emit({type:'pose-result',timestampMs:200,inferenceMs:20,poses:[]})
    for(let t=300;t<=6500;t+=100){
      await device.capture(video,t)
      full.emit({type:'pose-result',timestampMs:t,inferenceMs:20,poses:demoFrame(t,'conflict').poses})
    }
    const fast=motion.mock.calls.map(call=>call[0]).find(report=>report.events.length>0)
    expect(fast).toBeDefined()
    expect(result.mock.calls.map(call=>call[0]).some(report=>report.events.some((event:{id:string})=>event.id===fast.events[0].id))).toBe(true)
    device.dispose()
    expect(full.terminate).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('explicit detector experiment profiles',()=>{
  it.each([false,true])('routes source-matched crowd candidates only for an uncovered pair (fast coverage: %s)',async covered=>{
    vi.stubGlobal('createImageBitmap',vi.fn().mockImplementation(()=>Promise.resolve(bitmap())))
    const model={modelPath:'/models/validated.onnx',sha256:'0'.repeat(64),inputSide:416 as const,preferredDelegate:'CPU' as const}
    const result=vi.fn(),motion=vi.fn(),device=new DeviceVision(vi.fn(),result,'full','crowd',motion,vi.fn(),model,{experimentalProfile:'crowd-contact-sensitive'})
    device.start('CPU');const full=WorkerStub.all[0],crowd=WorkerStub.all[1]
    full.emit({type:'ready',delegate:'CPU'});crowd.emit({type:'ready',delegate:'CPU'});await Promise.resolve()
    const source={...video,currentTime:0} as HTMLVideoElement
    for(let t=100;t<=6500;t+=100){
      source.currentTime=t/1000
      const capture=device.capture(source,t);await Promise.resolve()
      const poses=demoFrame(t,'conflict').poses
      full.emit({type:'pose-result',timestampMs:t,inferenceMs:20,poses:covered?poses:[]})
      crowd.emit({type:'result',result:{timestampMs:t,inferenceMs:300,delegate:'CPU',poses,people:[{box:[.1,.1,.5,.9],score:.9},{box:[.5,.1,.9,.9],score:.9}]}})
      await capture
    }
    const fastAlerts=motion.mock.calls.flatMap(([report])=>report.events),crowdReports=result.mock.calls.map(([report])=>report),crowdAlerts=crowdReports.flatMap(report=>report.events)
    expect(fastAlerts.length+crowdAlerts.length).toBe(1)
    expect(crowdAlerts).toHaveLength(covered?0:1)
    for(const report of crowdReports)for(const event of report.events){expect(event.occurredAtMs).toBe(report.timestampMs);expect(report.poses).toHaveLength(2);expect(report.model).toBe('nivra-browser-rtmo-t-motion-v1')}
    device.dispose()
  })
  it('rejects an unknown experiment profile without starting a worker',()=>{
    expect(()=>new DeviceVision(vi.fn(),vi.fn(),'full','crowd',vi.fn(),vi.fn(),undefined,{experimentalProfile:'unapproved'})).toThrow('Unknown detector experiment profile')
    expect(WorkerStub.all).toHaveLength(0)
  })
})
