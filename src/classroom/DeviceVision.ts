import { ConflictEngine as OriginalConflictEngine } from '../lib/originalConflictEngine'
import { inferenceSize } from '../lib/inferenceSize'
import type { PoseLandmarks, VisionDelegate, VisionWorkerResponse } from '../types/vision'
import { DeviceAnalysis, CROWD_DEVICE_MODEL, DEVICE_POSE_LIMIT, type DeviceResult, type DeviceMotion, type DeviceStatus } from './deviceAnalysis'
import { analysisRegion, DeviceBudget, type AnalysisArea, type DeviceProfile } from './deviceBudget'
import { PeopleVision, type PersonObservation } from './PeopleVision'
import { CrowdPoseVision, type CrowdPoseModel } from './CrowdPoseVision'

const RETRY_DELAYS = [500, 1500, 3000] as const

/** Fresh pose frames use bounded proposal refreshes without queuing camera frames. */
export class DeviceVision {
  private motion: OriginalMotion | null = null
  private originalOnly = false
  private crowd: CrowdPoseVision | null = null
  private crowdProfile = false
  private crowdModel?: CrowdPoseModel
  private crowdFallback = false
  private crowdMediaTime = -Infinity
  private crowdObservationOnly = false
  private motionStarted = false
  private cachedMotionStatus: DeviceStatus | null = null
  private crowdObserved = false
  private crowdResultTimestamp = -Infinity
  private crowdPreferred: VisionDelegate = 'GPU'
  private worker: Worker | null = null
  private people: PeopleVision | null = null
  private analysis = new DeviceAnalysis()
  private disposed = false
  private ready = false
  private busy = false
  private generation = 0
  private lastCapture = -Infinity
  private lastPeopleCapture = -Infinity
  private peopleBusy = false
  private proposals: PersonObservation[] | null = null
  private pending: { timestamp: number; aspect: number; startedAt: number; waitedForPeople: boolean; poses?: PoseLandmarks[]; people?: PersonObservation[]; poseMs?: number; peopleMs?: number; bitmap?: ImageBitmap } | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private cpuRetries = 0
  private delegate: VisionDelegate = 'GPU'
  readonly budget = new DeviceBudget()
  private area: AnalysisArea
  private onStatus: (status: DeviceStatus) => void
  private onResult: (result: DeviceResult) => void

  constructor(onStatus: (status: DeviceStatus) => void, onResult: (result: DeviceResult) => void, area: AnalysisArea = 'full', profile: DeviceProfile | 'crowd' = 'balanced', onMotion?: (result: DeviceMotion) => void, onMotionStatus?: (status: DeviceStatus) => void, crowdModel?: CrowdPoseModel) {
    this.onStatus = onStatus
    this.onResult = onResult
    this.area = area
    this.originalOnly = profile === 'original'
    this.crowdProfile = profile === 'crowd'
    this.crowdModel = crowdModel
    if (this.crowdProfile) {
      this.analysis = new DeviceAnalysis(new OriginalConflictEngine({cooldownScope:'pair'}),CROWD_DEVICE_MODEL)
      this.crowdObservationOnly = !!onMotion
      if (onMotion) this.motion = new OriginalMotion(result => {
        onMotion(result)
        if (this.crowdFallback) {
          this.budget.observe(result.inferenceMs)
          this.onResult({...result,type:'device-result'})
        }
      },area,status => {
        this.cachedMotionStatus = status
        onMotionStatus?.(status)
        if (this.crowdFallback) this.onStatus({...status,detail:`Crowd detection unavailable. ${status.detail}`})
      },'pair')
      return
    }
    if (this.originalOnly) {
      this.motion = new OriginalMotion(result => {
        this.budget.observe(result.inferenceMs)
        this.onResult({ ...result, type: 'device-result' })
      }, area, onStatus)
    } else if (onMotion) this.motion = new OriginalMotion(onMotion, area, onMotionStatus)
  }

  start(preferred: VisionDelegate = 'GPU') {
    if (this.disposed) return
    if (this.crowdProfile) {
      if (this.motion && !this.motionStarted) { this.motionStarted = true; this.motion.start(preferred) }
      this.crowdPreferred = preferred; void this.startCrowd(); return
    }
    this.cpuRetries = 0
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    if (this.motion) { this.motion.start(preferred); preferred = 'CPU' }
    if (!this.originalOnly) this.initialize(preferred)
  }

  private async startCrowd() {
    if (this.crowd || this.crowdFallback) return
    this.onStatus({state:'loading',delegate:null,detail:'Loading multi-person pose detection on this device…'})
    if (!this.crowdModel) { this.fallbackCrowd(); return }
    const crowd = new CrowdPoseVision({...this.crowdModel,preferredDelegate:this.crowdModel.preferredDelegate ?? this.crowdPreferred})
    this.crowd = crowd
    try {
      await crowd.start()
      if (this.disposed || this.crowd !== crowd) return
      this.ready = true
      this.onStatus({state:'loading',delegate:crowd.delegate,detail:'Starting crowd detection. Preparing the first real camera frame…'})
    } catch { if (!this.disposed && this.crowd === crowd) this.fallbackCrowd() }
  }

  private fallbackCrowd() {
    if (this.disposed || this.crowdFallback) return
    this.crowdFallback = true; this.ready = false; this.busy = false
    this.crowd?.dispose(); this.crowd = null
    if (this.motion) {
      const status = this.cachedMotionStatus ?? {state:'loading' as const,delegate:null,detail:'Starting original full-model motion tracking…'}
      this.onStatus({...status,detail:`Crowd detection unavailable. ${status.detail}`})
      return
    }
    this.motion = new OriginalMotion(result => {
      this.budget.observe(result.inferenceMs)
      this.onResult({...result,type:'device-result'})
    }, this.area, status => this.onStatus({...status,detail:`Crowd detection unavailable. ${status.detail}`}))
    this.motion.start(this.crowdModel?.preferredDelegate ?? this.crowdPreferred)
  }

  private async captureCrowd(video: HTMLVideoElement, timestamp: number) {
    const crowd = this.crowd
    if (this.disposed || !this.ready || !crowd || this.busy || timestamp - this.lastCapture < 50 || video.readyState < 2 || !video.videoWidth) return
    if (typeof video.currentTime === 'number' && video.currentTime === this.crowdMediaTime) return
    this.crowdMediaTime = video.currentTime
    this.busy = true; this.lastCapture = timestamp
    let bitmap: ImageBitmap | null = null
    try {
      const region = analysisRegion(this.area)
      const x = Math.round(video.videoWidth * region.x), width = Math.max(1,Math.round(video.videoWidth * region.width)), height = video.videoHeight
      const size = inferenceSize({width,height},1280)
      bitmap = await createImageBitmap(video,x,0,width,height,{resizeWidth:size.width,resizeHeight:size.height,resizeQuality:'high'})
      if (this.disposed || this.crowd !== crowd) { bitmap.close(); return }
      const owned = bitmap; bitmap = null
      const result = await crowd.analyze(owned,timestamp)
      if (this.disposed || this.crowd !== crowd) return
      this.budget.observe(result.inferenceMs)
      if (!this.crowdObserved) {
        this.crowdObserved = true
        this.onStatus({state:'ready',delegate:'CPU',detail:'RTMO single-pass crowd observation · browser WASM CPU · up to 32 observed people'})
      }
      const people = result.people.map(person => ({...person,box:[region.x+person.box[0]*region.width,person.box[1],region.x+person.box[2]*region.width,person.box[3]] as [number,number,number,number]}))
      const report = this.analysis.update(timestamp,result.inferenceMs,result.poses,width/height,result.delegate ?? crowd.delegate,this.area,people)
      const interval = timestamp - this.crowdResultTimestamp
      this.crowdResultTimestamp = timestamp
      // Preserve the original rules’ 600ms continuity limit. A slow crowd pass
      // may still observe people, but cannot establish fast arm-motion evidence.
      if (this.crowdObservationOnly) {
        this.onResult({...report,usablePeople:0,events:[],conflict:{status:'limited',explanation:'Crowd skeletons show observed people. Fast motion checks run separately on up to 4 poses.'}})
        return
      }
      this.onResult((result.inferenceMs > 600 || (Number.isFinite(interval) && interval > 600)) && report.conflict.status !== 'alert'
        ? {...report,conflict:{status:'limited',explanation:'Crowd pose updates exceed the original 600ms motion window. Video and observed people remain available; fast conflict evidence is limited.'}} : report)
    } catch { bitmap?.close(); if (!this.disposed && this.crowd === crowd) this.fallbackCrowd() }
    finally { if (this.crowd === crowd) this.busy = false }
  }

  private initialize(preferred: VisionDelegate) {
    if (this.disposed) return
    this.generation++
    const epoch = this.generation
    this.worker?.terminate()
    this.people?.dispose()
    if (this.timer) clearTimeout(this.timer)
    this.ready = false
    this.busy = false
    this.peopleBusy = false
    this.proposals = null
    this.lastPeopleCapture = -Infinity
    this.pending?.bitmap?.close()
    this.pending = null
    this.analysis = new DeviceAnalysis()
    this.onStatus({ state: 'loading', delegate: null, detail: this.cpuRetries ? `Retrying detection (${this.cpuRetries}/3)` : preferred === 'GPU' ? 'Loading person and pose detection on this device…' : 'Starting pose CPU fallback and person detection…' })
    const fail = () => {
      if (this.disposed || this.generation !== epoch) return
      if (preferred === 'GPU') this.initialize('CPU')
      else this.fatal('Device analysis failed. Video can still stream; reconnect to retry detection.')
    }
    try {
      const worker = new Worker(new URL('../workers/vision.worker.ts', import.meta.url), { type: 'module' })
      const people = new PeopleVision()
      this.worker = worker
      this.people = people
      let poseReady = false, peopleReady = false
      const ready = () => {
        if (this.disposed || this.generation !== epoch || !poseReady || !peopleReady) return
        if (this.timer) clearTimeout(this.timer)
        this.ready = true
        this.onStatus({ state: 'ready', delegate: this.delegate, detail: `Pose ${this.delegate} + person CPU · observed boxes and motion coverage reported separately` })
      }
      this.timer = setTimeout(fail, 30000)
      worker.onerror = fail
      worker.onmessageerror = fail
      worker.onmessage = ({ data }: MessageEvent<VisionWorkerResponse>) => {
        if (this.disposed || this.worker !== worker) return
        if (data.type === 'error') { fail(); return }
        if (data.type === 'ready') {
          this.delegate = data.delegate
          poseReady = true
          ready()
        }
        if (data.type === 'pose-result' && data.timestampMs === this.pending?.timestamp && this.pending.bitmap === undefined) {
          this.pending.poses = data.poses
          this.pending.poseMs = data.inferenceMs
          this.completeFrame()
        }
      }
      void people.start().then(() => { peopleReady = true; ready() }).catch(reason => {
        if (this.disposed || this.generation !== epoch) return
        this.fatal(reason instanceof Error ? reason.message : 'Person detection could not start. Reconnect to retry.')
      })
      worker.postMessage({
        type: 'init', task: 'pose', poseDelegate: preferred,
        modelPath: `${import.meta.env.BASE_URL}models/pose_landmarker_lite.task`,
        wasmRoot: import.meta.env.DEV ? `${import.meta.env.BASE_URL}__nivra_wasm` : `${import.meta.env.BASE_URL}mediapipe/wasm`,
        maxPoses: DEVICE_POSE_LIMIT, poseConfidence: 0.5, objectConfidence: 0.35,
        portraitMultiPerson: this.area === 'full', personProposalPose: true,
      })
    } catch { fail() }
  }

  private completeFrame() {
    const pending = this.pending
    if (!pending || pending.poses === undefined) return
    if (this.timer) clearTimeout(this.timer)
    this.pending = null
    this.busy = false
    // Include elapsed capture/transfer/model work, while person refresh can run independently.
    const elapsed = Math.max(pending.poseMs ?? 0, pending.waitedForPeople ? (pending.peopleMs ?? 0) + (pending.poseMs ?? 0) : pending.peopleMs ?? 0, performance.now() - pending.startedAt)
    this.budget.observe(elapsed)
    this.onResult(this.analysis.update(pending.timestamp, elapsed, pending.poses, pending.aspect, this.delegate, this.area, pending.people))
  }

  private fatal(_detail: string) {
    this.ready = false; this.generation++
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate(); this.people?.dispose()
    this.pending?.bitmap?.close()
    this.worker = null; this.people = null; this.pending = null
    if (this.cpuRetries >= RETRY_DELAYS.length) {
      this.onStatus({ state: 'error', delegate: null, detail: 'Detection unavailable. Retry detection.' })
      return
    }
    const delay = RETRY_DELAYS[this.cpuRetries++]
    const epoch = this.generation
    this.onStatus({ state: 'loading', delegate: null, detail: `Retrying detection (${this.cpuRetries}/3)` })
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      if (!this.disposed && epoch === this.generation) this.initialize('CPU')
    }, delay)
  }

  async capture(video: HTMLVideoElement, timestamp: number) {
    void this.motion?.capture(video, timestamp)
    if (this.crowdProfile) { if (!this.crowdFallback) await this.captureCrowd(video,timestamp); return }
    if (this.originalOnly) return
    if (this.disposed || !this.ready || this.busy || timestamp - this.lastCapture < 50 || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return
    this.busy = true
    this.lastCapture = timestamp
    const generation = this.generation
    const startedAt = performance.now()
    let full: ImageBitmap | null = null, pose: ImageBitmap | null = null
    try {
      const region = analysisRegion(this.area)
      const fullSize = inferenceSize({ width: video.videoWidth, height: video.videoHeight }, 1280)
      full = await createImageBitmap(video, { resizeWidth: fullSize.width, resizeHeight: fullSize.height, resizeQuality: 'low' })
      if (this.disposed || generation !== this.generation) { full.close(); return }
      const width = Math.max(1, Math.round(full.width * region.width)), height = Math.max(1, Math.round(full.height * region.height))
      const size = inferenceSize({ width, height }, 1280)
      // Derive the pose crop from the SAME captured pixels used by person detection.
      pose = await createImageBitmap(full, Math.round(full.width * region.x), Math.round(full.height * region.y), width, height,
        { resizeWidth: size.width, resizeHeight: size.height, resizeQuality: 'low' })
      if (this.disposed || generation !== this.generation) { full.close(); pose.close(); return }
      this.pending = { timestamp, aspect: width / height, startedAt, waitedForPeople: this.proposals === null, bitmap: pose }
      pose = null
      this.timer = setTimeout(() => {
        if (this.delegate === 'GPU') this.initialize('CPU')
        else this.fatal('Device analysis stalled. Video only; reconnect to retry detection.')
      }, this.delegate === 'GPU' ? 15000 : 30000)
      const refresh = !this.peopleBusy && (this.proposals === null || timestamp - this.lastPeopleCapture >= 500)
      if (this.proposals !== null) this.sendPose(this.proposals)
      if (refresh) {
        this.peopleBusy = true
        this.lastPeopleCapture = timestamp
        const personResult = this.people!.analyze(full, timestamp)
        full = null // PeopleVision owns this bitmap on success and rejection.
        void personResult.then(result => {
          if (this.disposed || generation !== this.generation) return
          this.peopleBusy = false
          this.proposals = result.people
          if (this.pending?.timestamp === result.timestampMs) {
            this.pending.people = result.people
            this.pending.peopleMs = result.inferenceMs
          }
          // A late detector updates crop proposals only. Its boxes never become
          // observations on a different camera timestamp.
          if (this.pending?.bitmap) this.sendPose(result.people)
        }).catch(reason => {
          if (this.disposed || generation !== this.generation) return
          this.fatal(reason instanceof Error ? reason.message : 'Person detection failed. Reconnect to retry.')
        })
      } else { full.close(); full = null }

    } catch {
      full?.close()
      pose?.close()
      if (this.disposed || generation !== this.generation) return
      this.fatal('This browser cannot process camera frames. Video only; try a current browser.')
    }
  }

  private sendPose(people: PersonObservation[]) {
    const pending = this.pending
    if (!pending?.bitmap) return
    const region = analysisRegion(this.area)
    const personRegions = people.flatMap(person => {
      const [x1, y1, x2, y2] = person.box
      const center = (x1 + x2) / 2
      if (center < region.x || center > region.x + region.width) return []
      return [[Math.max(0, (x1 - region.x) / region.width), y1, Math.min(1, (x2 - region.x) / region.width), y2] as [number, number, number, number]]
    })
    const bitmap = pending.bitmap
    this.worker!.postMessage({ type: 'frame', bitmap, timestampMs: pending.timestamp, personRegions }, [bitmap])
    pending.bitmap = undefined
  }

  dispose() {
    this.motion?.dispose()
    this.crowd?.dispose(); this.crowd = null
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    this.disposed = true
    this.ready = false
    this.generation++
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate()
    this.people?.dispose()
    this.worker = null
    this.people = null
    this.pending?.bitmap?.close()
    this.pending = null
  }
}


/** Original full-model VIDEO tracking, independent of crowd detection and ROI work. */
class OriginalMotion {
  private worker: Worker | null = null
  private ready = false
  private busy = false
  private disposed = false
  private epoch = 0
  private lastCapture = -Infinity
  private lastMediaTime = -Infinity
  private delegate: VisionDelegate = 'GPU'
  private analysis = new DeviceAnalysis(new OriginalConflictEngine())
  private cooldownScope: 'camera' | 'pair' = 'camera'
  private pending: { timestamp: number; aspect: number; startedAt: number } | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private cpuRetries = 0
  private onResult: (result: DeviceMotion) => void
  private area: AnalysisArea
  private onStatus?: (status: DeviceStatus) => void
  constructor(onResult: (result: DeviceMotion) => void, area: AnalysisArea, onStatus?: (status: DeviceStatus) => void, cooldownScope: 'camera' | 'pair' = 'camera') {
    this.onResult = onResult; this.area = area; this.onStatus = onStatus
    this.cooldownScope = cooldownScope
    this.analysis = new DeviceAnalysis(new OriginalConflictEngine({cooldownScope}))
  }

  start(preferred: VisionDelegate) {
    if (this.disposed) return
    this.cpuRetries = 0
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    this.initialize(preferred)
  }

  private initialize(preferred: VisionDelegate) {
    const epoch = ++this.epoch
    this.onStatus?.({ state: 'loading', delegate: null, detail: this.cpuRetries ? `Retrying detection (${this.cpuRetries}/3)` : preferred === 'GPU' ? 'Loading original full-model motion tracking…' : 'Starting full-model motion CPU fallback…' })
    this.worker?.terminate()
    if (this.timer) clearTimeout(this.timer)
    this.ready = false; this.busy = false; this.pending = null
    this.lastMediaTime = -Infinity
    this.analysis = new DeviceAnalysis(new OriginalConflictEngine({cooldownScope:this.cooldownScope}))
    const fail = () => {
      if (this.disposed || epoch !== this.epoch) return
      if (preferred === 'GPU') this.initialize('CPU')
      else this.fatal('Motion tracking failed. Crowd analysis can continue; reconnect to retry motion.')
    }
    try {
      const worker = new Worker(new URL('../workers/vision.worker.ts', import.meta.url), { type: 'module' })
      this.worker = worker
      worker.onerror = fail; worker.onmessageerror = fail
      this.timer = setTimeout(fail, 30000)
      worker.onmessage = ({ data }: MessageEvent<VisionWorkerResponse>) => {
        if (this.disposed || epoch !== this.epoch) return
        if (data.type === 'error') { fail(); return }
        if (data.type === 'ready') {
          if (this.timer) clearTimeout(this.timer)
          this.delegate = data.delegate; this.ready = true
          this.onStatus?.({ state: 'ready', delegate: data.delegate, detail: `Original full-model VIDEO motion tracking · ${data.delegate} · up to4 poses` })
        }
        if (data.type === 'pose-result' && data.timestampMs === this.pending?.timestamp) {
          const pending = this.pending
          if (this.timer) clearTimeout(this.timer)
          this.pending = null; this.busy = false
          const elapsed = Math.max(data.inferenceMs, performance.now() - pending.startedAt)
          const result = this.analysis.update(pending.timestamp, elapsed, data.poses, pending.aspect, this.delegate, this.area)
          this.onResult({ ...result, type: 'device-motion' })
        }
      }
      worker.postMessage({ type: 'init', task: 'pose', poseDelegate: preferred,
        modelPath: `${import.meta.env.BASE_URL}models/pose_landmarker_full.task`,
        wasmRoot: import.meta.env.DEV ? `${import.meta.env.BASE_URL}__nivra_wasm` : `${import.meta.env.BASE_URL}mediapipe/wasm`,
        maxPoses: 4, poseConfidence: .5, objectConfidence: .35,
        personProposalPose: false, portraitMultiPerson: false })
    } catch { fail() }
  }

  async capture(video: HTMLVideoElement, timestamp: number) {
    if (this.disposed || !this.ready || this.busy || timestamp - this.lastCapture < 50 || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return
    if (Number.isFinite(video.currentTime) && video.currentTime === this.lastMediaTime) return
    this.lastMediaTime = video.currentTime
    this.busy = true; this.lastCapture = timestamp
    const epoch = this.epoch, startedAt = performance.now(), region = analysisRegion(this.area)
    const width = Math.max(1, Math.round(video.videoWidth * region.width))
    const height = Math.max(1, Math.round(video.videoHeight * region.height))
    const size = inferenceSize({ width, height }, 960)
    let bitmap: ImageBitmap | null = null
    try {
      bitmap = await createImageBitmap(video, Math.round(video.videoWidth * region.x), Math.round(video.videoHeight * region.y), width, height,
        { resizeWidth: size.width, resizeHeight: size.height, resizeQuality: 'medium' })
      if (this.disposed || epoch !== this.epoch) { bitmap.close(); return }
      this.pending = { timestamp, aspect: width / height, startedAt }
      this.timer = setTimeout(() => {
        if (this.disposed || epoch !== this.epoch) return
        if (this.delegate === 'GPU') this.initialize('CPU')
        else this.fatal('Motion tracking stalled. Crowd analysis can continue; reconnect to retry motion.')
      }, this.delegate === 'GPU' ? 5000 : 10000)
      this.worker!.postMessage({ type: 'frame', bitmap, timestampMs: timestamp }, [bitmap])
      bitmap = null
    } catch {
      bitmap?.close()
      if (!this.disposed && epoch === this.epoch) this.fatal('Camera frames could not reach motion tracking. Crowd analysis can continue.')
    }
  }

  private fatal(_detail: string) {
    this.ready = false; this.busy = false; this.epoch++
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate(); this.worker = null; this.pending = null
    if (this.cpuRetries >= RETRY_DELAYS.length) {
      this.onStatus?.({ state: 'error', delegate: null, detail: 'Motion unavailable. Retry detection.' })
      return
    }
    const delay = RETRY_DELAYS[this.cpuRetries++]
    const epoch = this.epoch
    this.onStatus?.({ state: 'loading', delegate: null, detail: `Retrying detection (${this.cpuRetries}/3)` })
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      if (!this.disposed && epoch === this.epoch) this.initialize('CPU')
    }, delay)
  }

  dispose() {
    this.disposed = true; this.ready = false; this.epoch++
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    if (this.timer) clearTimeout(this.timer)
    this.worker?.terminate(); this.worker = null; this.pending = null
  }
}
