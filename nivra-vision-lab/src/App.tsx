import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import { ObservationRail } from './components/ObservationRail'
import { ConflictPanel } from './components/ConflictPanel'
import { useVisionSession } from './hooks/useVisionSession'
import type { CameraStatus } from './lib/cameraState'
import type { DemoScenario } from './lib/demoScene'
import type { PoseQuality } from './types/vision'
import { ReviewTonePlayer, type ReviewAudioState } from './services/ReviewTonePlayer'

const CAMERA_LABELS: Record<CameraStatus, string> = {
  unsupported: 'Camera unsupported',
  idle: 'Camera ready',
  requesting: 'Opening source',
  live: 'Camera live',
  'permission-denied': 'Camera permission blocked',
  'not-found': 'No camera found',
  interrupted: 'Camera interrupted',
  error: 'Source unavailable',
}

function App() {
  const session = useVisionSession()
  const { camera, vision, metrics } = session
  const scene = {
    ...session.scene,
    events: [...session.scene.events, ...session.conflict.events].sort((a, b) => b.occurredAtMs - a.occurredAtMs).slice(0, 10),
  }
  const fileInputRef = useRef<HTMLInputElement>(null)
  const audioRef = useRef<ReviewTonePlayer | null>(null)
  const soundEnabledRef = useRef(true)
  const audioActionRef = useRef(0)
  const seenEventsRef = useRef(new Set<string>())
  const [soundAlerts, setSoundAlerts] = useState(true)
  const [audioState, setAudioState] = useState<ReviewAudioState>('idle')
  const [soundNotice, setSoundNotice] = useState<string | null>(null)
  const [acknowledged, setAcknowledged] = useState<ReadonlySet<string>>(new Set())

  const getAudio = useCallback(() => {
    if (!audioRef.current || audioRef.current.getState() === 'disposed') audioRef.current = new ReviewTonePlayer()
    return audioRef.current
  }, [])

  useEffect(() => () => {
    audioActionRef.current += 1
    audioRef.current?.dispose()
    audioRef.current = null
  }, [])

  useEffect(() => {
    audioRef.current?.stop()
    seenEventsRef.current.clear()
    setAcknowledged(new Set())
    setSoundNotice(null)
  }, [session.sessionId])

  useEffect(() => {
    const unseen = scene.events.filter(event => !seenEventsRef.current.has(event.id))
    unseen.forEach(event => seenEventsRef.current.add(event.id))
    const completedReview = session.kind === 'clip' && session.clipMode === 'review' &&
      session.scanProgress.duration > 0 && session.scanProgress.currentTime >= session.scanProgress.duration
    // React can batch the final result with scan completion. That confirmed
    // event still sounds; an explicit pause/stop is not a completed scan.
    if (!unseen.length || !soundEnabledRef.current || (!session.playing && !completedReview) || camera.status !== 'live') return
    const audio = getAudio()
    const action = ++audioActionRef.current
    void audio.play(unseen[0].type).then(() => {
      if (audioActionRef.current !== action || !soundEnabledRef.current) return
      const state = audio.getState()
      setAudioState(state)
      if (state === 'blocked' || state === 'unsupported') {
        setSoundNotice(state === 'unsupported'
          ? 'Audio is unavailable in this browser. The review queue stays active.'
          : 'Sound is blocked. Click Test sound to enable it.')
      }
    })
  }, [scene.events, getAudio, session.playing, session.kind, session.clipMode, session.scanProgress, camera.status])

  const prepareAudio = () => {
    audioActionRef.current += 1
    audioRef.current?.stop()
    setSoundNotice(null)
    if (!soundEnabledRef.current) return
    const audio = getAudio()
    const action = audioActionRef.current
    void audio.prime().then(() => {
      if (audioActionRef.current === action && soundEnabledRef.current) setAudioState(audio.getState())
    })
  }

  const startCamera = (deviceId?: string) => {
    prepareAudio()
    void session.startCamera(deviceId)
  }

  const startDemo = (scenario: DemoScenario = 'conflict') => {
    prepareAudio()
    session.startDemo(scenario)
  }

  const stop = () => {
    audioActionRef.current += 1
    audioRef.current?.stop()
    session.stop()
  }

  const acknowledge = (id: string) => {
    audioActionRef.current += 1
    audioRef.current?.stop()
    setAcknowledged(previous => new Set([...previous, id]))
  }

  const toggleSound = (enabled: boolean) => {
    audioActionRef.current += 1
    soundEnabledRef.current = enabled
    setSoundAlerts(enabled)
    setSoundNotice(null)
    if (enabled) prepareAudio()
    else audioRef.current?.stop()
  }

  const testSound = async () => {
    const action = ++audioActionRef.current
    const audio = getAudio()
    setSoundNotice('Starting test tone…')
    const scheduled = await audio.playPreview()
    if (audioActionRef.current !== action) return
    const state = audio.getState()
    setAudioState(state)
    setSoundNotice(scheduled
      ? 'Test tone started. Check your speaker volume if you did not hear it.'
      : state === 'unsupported'
        ? 'Audio is unavailable in this browser. Try Chrome for sound alerts.'
        : "Sound could not start. Click Test sound again and check this site's sound permission.")
  }

  const isLive = camera.status === 'live'
  const isDemo = session.kind === 'demo'
  const isClip = session.kind === 'clip'
  const clipSettingsLocked = isClip && (isLive || camera.status === 'requesting')
  const isReviewScan = isClip && session.clipMode === 'review'
  const scanComplete = isReviewScan && session.scanProgress.duration > 0 &&
    session.scanProgress.currentTime >= session.scanProgress.duration
  const canStart = vision.status === 'ready' && camera.status !== 'requesting' && camera.status !== 'unsupported'
  const activeReview = scene.events.find(event => !acknowledged.has(event.id))
  const analysisLabel = isDemo && isLive ? 'Simulated observations'
    : vision.status === 'loading' ? 'Loading local models'
      : vision.status === 'error' ? 'Analysis unavailable'
        : !isLive ? 'Waiting for camera'
          : !session.playing ? scanComplete ? 'Review complete' : 'Video paused'
            : session.stalled ? 'Analysis stalled'
              : !metrics.fps ? 'Starting analysis'
                : 'Analysis running'
  const sourceLabel = isLive && isDemo ? 'Test scenario'
    : isLive && isClip ? isReviewScan
      ? scanComplete ? 'Review complete' : session.playing ? 'Review running' : 'Review paused'
      : session.playing ? 'Video playing' : 'Video paused'
      : CAMERA_LABELS[camera.status]
  const sourceError = session.fileError ?? camera.message
  const watch = scene.watch
  const audioLabel = !soundAlerts ? 'Sound off'
    : audioState === 'ready' ? 'Sound ready'
      : audioState === 'blocked' ? 'Sound needs permission'
        : audioState === 'unsupported' ? 'Audio unavailable'
          : 'Sound enabled'

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup" aria-label="NIVRA Vision">
          <span className="brand-symbol" aria-hidden="true"><i /><i /><i /></span>
          <span className="wordmark">NIVRA</span>
          <span className="product-name">Vision</span>
        </div>
        <div className="privacy-note"><span aria-hidden="true" />On-device processing</div>
      </header>

      <main className="workspace">
        <div className="workspace-heading">
          <div><h1>Live workspace</h1><p>Watch movement. Review possible physical conflict.</p></div>
          <div className="heading-actions">
            <label className="toggle-control">
              <input type="checkbox" checked={soundAlerts} onChange={event => toggleSound(event.target.checked)} data-testid="sound-alerts" />
              <span className="toggle-track" aria-hidden="true"><span /></span>
              Sound alerts
            </label>
            <button className="text-button" type="button" onClick={() => void testSound()}>Test sound</button>
            <span className="source-caption" data-testid="sound-status">{audioLabel}</span>
          </div>
        </div>
        {soundNotice ? <p className="notice" role="status">{soundNotice}</p> : null}

        <div className="workspace-grid">
          <section className="camera-module" aria-label="Vision workspace">
            <div className="source-bar">
              <div className="source-tabs" aria-label="Input source">
                <button type="button" className={session.kind === 'camera' ? 'is-selected' : ''} aria-pressed={session.kind === 'camera'} onClick={() => startCamera()} disabled={!canStart}>Camera</button>
                <button type="button" className={isClip ? 'is-selected' : ''} aria-pressed={isClip} disabled={vision.status !== 'ready'} onClick={() => fileInputRef.current?.click()}>Video file</button>
                <button type="button" className={isDemo ? 'is-selected' : ''} aria-pressed={isDemo} onClick={() => startDemo()}>Test scenario</button>
              </div>
              <span className="source-caption">{isLive ? session.sourceName : 'Choose a local source'}</span>
              <input
                ref={fileInputRef}
                className="file-input"
                type="file"
                accept="video/*"
                data-testid="clip-input"
                aria-label="Open local video"
                onChange={event => {
                  const file = event.target.files?.[0]
                  if (file) { prepareAudio(); void session.openClip(file) }
                  event.target.value = ''
                }}
              />
            </div>

            <div className="camera-stage" ref={session.stageRef}>
              <video
                ref={session.videoRef}
                className={`camera-video ${session.kind === 'camera' && session.mirrored ? 'is-mirrored' : ''} ${isClip ? 'is-clip' : ''} ${isDemo ? 'is-hidden' : ''}`}
                autoPlay muted playsInline
                data-testid="camera-video"
                onEnded={() => { audioRef.current?.stop(); session.setPlaying(false) }}
              />
              <canvas ref={session.demoCanvasRef} className={`demo-canvas ${isDemo && isLive ? '' : 'is-hidden'}`} aria-hidden="true" />
              <canvas ref={session.canvasRef} className="vision-canvas" aria-hidden="true" data-testid="pose-canvas" />

              <div className="stage-statusbar">
                <span className={`status-chip ${isLive ? 'is-live' : ''}`} data-testid="camera-status"><span className="status-dot" aria-hidden="true" />{sourceLabel}</span>
                {typeof document !== 'undefined' && document.fullscreenEnabled ? (
                  <button className="stage-button" type="button" aria-label="Expand camera view" onClick={() => {
                    if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined)
                    else void session.stageRef.current?.requestFullscreen().catch(() => undefined)
                  }}>
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5" /></svg>
                  </button>
                ) : null}
              </div>

              {!isLive ? (
                <div className="camera-empty-state">
                  <div className="focus-glyph" aria-hidden="true"><span /><span /><span /><span /></div>
                  <h2>{camera.status === 'requesting' ? 'Opening your source' : sourceError ? 'Camera setup needs attention' : 'A clear view starts here'}</h2>
                  <p>{sourceError ?? 'Keep both people’s shoulders and hands in view. Legs can be out of frame. All analysis stays on this device.'}</p>
                  <div className="empty-actions">
                    <button className="primary-action" type="button" onClick={() => startCamera()} disabled={!canStart} data-testid="start-camera">
                      {camera.status === 'requesting' ? 'Opening camera…' : vision.status === 'loading' ? 'Preparing models…' : 'Start camera'}
                    </button>
                    <button className="secondary-action" type="button" onClick={() => startDemo()}>Try test scenario</button>
                  </div>
                  {camera.status === 'requesting' ? <button className="stage-button cancel-input" type="button" onClick={stop}>Cancel</button> : null}
                </div>
              ) : null}

              {isLive && !isDemo && (vision.status === 'error' || session.stalled) ? (
                <div className="analysis-error" role="status">
                  <strong>{session.stalled ? 'Analysis stopped responding' : 'Analysis unavailable'}</strong>
                  <p>{vision.error ?? 'The video is still open. Restart the local models to continue.'}</p>
                  <button className="secondary-action" type="button" onClick={session.retryAnalysis}>Restart analysis</button>
                </div>
              ) : null}

              {isLive ? <div className="live-caption"><span>{metrics.poses}</span> {metrics.poses === 1 ? 'person' : 'people'}<i aria-hidden="true" /><span>{scene.objects.length}</span> {scene.objects.length === 1 ? 'object' : 'objects'}</div> : null}
              {isLive && isDemo ? <div className="simulation-stamp">Scripted test</div> : null}
              {isLive && activeReview ? (
                <div className="stage-review-alert" role="alert" data-testid="review-alert">
                  <div><span className="review-label">{isDemo ? 'Test event · human review' : 'Human review'}</span><strong>{activeReview.title}</strong><p>{activeReview.objectName}. Check the scene before acting.</p></div>
                  <button className="review-action" type="button" onClick={() => acknowledge(activeReview.id)}>Acknowledge</button>
                </div>
              ) : null}
            </div>

            {isLive && isDemo ? (
              <div className="notice"><strong>Scripted scene. Tests alert rules, not model accuracy.</strong><span>{session.scenario === 'conflict' ? 'Repeated directed arm movements. A review follows after the motion is confirmed.' : session.scenario === 'calm' ? 'Two people standing and waving. The conflict detector should stay quiet.' : session.scenario === 'watched' ? 'Backpack is watched. It moves after seven seconds.' : `The person leaves. An unattended-bag alert follows after ${session.unattendedSeconds} seconds without someone nearby.`}</span></div>
            ) : null}

            {isLive && isReviewScan ? (
              <div className="notice" data-testid="clip-review-progress" role="status">
                <strong>{scanComplete ? 'Review complete' : 'Frame-by-frame review'} · {session.scanProgress.currentTime.toFixed(1)} / {session.scanProgress.duration.toFixed(1)} s · {session.scanProgress.analyzedFrames} samples</strong>
                <span>CPU reference scan at 40 ms video intervals. Waits for each result, so playback can be slower. Motion uses the original video timing. {session.clipSensitivity === 'early' ? 'Early review is on.' : 'Standard review is on.'}</span>
              </div>
            ) : null}

            <div className="control-rail">
              <div className="source-control">
                {isDemo ? <><label htmlFor="scenario-select">Scenario</label><select id="scenario-select" data-testid="demo-scenario" value={session.scenario} onChange={event => startDemo(event.target.value as DemoScenario)}><option value="conflict">Repeated striking motion</option><option value="calm">Waving · no conflict</option><option value="watched">Watched item moves</option><option value="unattended">Bag left behind</option></select></> : isClip ? <span className="source-caption">{session.sourceName}</span> : <>
                  <label htmlFor="camera-select">Camera</label>
                  <select id="camera-select" value={session.deviceId} disabled={camera.status === 'requesting'} onChange={event => {
                    session.setDeviceId(event.target.value)
                    if (isLive) startCamera(event.target.value)
                  }}>
                    {!session.devices.length ? <option value="">Default camera</option> : null}
                    {session.devices.map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
                  </select>
                </>}
              </div>
              <div className="toggle-controls" aria-label="View controls">
                <label className="toggle-control"><input type="checkbox" checked={session.mirrored && session.kind === 'camera'} disabled={session.kind !== 'camera'} onChange={event => session.setMirrored(event.target.checked)} /><span className="toggle-track" aria-hidden="true"><span /></span>Mirror</label>
                <label className="toggle-control"><input type="checkbox" checked={session.skeleton} onChange={event => session.setSkeleton(event.target.checked)} /><span className="toggle-track" aria-hidden="true"><span /></span>Skeleton</label>
                <label className="toggle-control"><input type="checkbox" checked={session.objectsVisible && (session.objectAnalysisEnabled || isDemo)} disabled={!session.objectAnalysisEnabled && !isDemo} onChange={event => session.setObjectsVisible(event.target.checked)} /><span className="toggle-track" aria-hidden="true"><span /></span>Objects</label>
              </div>
              <div className="playback-actions">
                {isLive && isClip ? <button className="text-button" type="button" disabled={vision.status !== 'ready'} onClick={() => { audioRef.current?.stop(); void session.togglePlayback() }}>{vision.status !== 'ready' ? 'Waiting for analysis…' : session.playing ? 'Pause' : scanComplete ? 'Replay' : 'Resume'}</button> : null}
                {isLive && isDemo ? <button className="text-button" type="button" onClick={() => startDemo(session.scenario)}>Replay</button> : null}
                <button className="secondary-action" type="button" disabled={!isLive && !canStart} onClick={isLive ? stop : () => startCamera()} data-testid={isLive ? 'stop-camera' : 'rail-start-camera'}>{isLive ? 'Stop' : 'Start camera'}</button>
              </div>
            </div>

            {session.objectAnalysisEnabled || isDemo && ['watched', 'unattended'].includes(session.scenario) ? <div className={`watch-bar ${watch?.state === 'watching' ? 'is-armed' : ''}`}>
              <span className="watch-indicator" aria-hidden="true" />
              <div><strong>{watch ? `${watch.displayName} · ${watch.state === 'watching' ? 'watching position' : watch.state === 'moved' ? 'movement detected' : 'left view'}` : 'Watch an item'}</strong><p>{watch ? 'Alerts when this item moves or is no longer visible.' : 'Select Watch item beside an object to monitor its current position.'}</p></div>
              {watch ? <>
                {watch.state !== 'watching' && scene.objects.some(item => item.trackKey === watch.trackKey) ? <button className="text-button" type="button" onClick={() => session.watch(watch.trackKey)}>Rearm</button> : null}
                <button className="text-button" type="button" onClick={session.clearWatch}>Clear watch</button>
              </> : null}
            </div> : null}

            <section className="diagnostics" aria-label="Analysis diagnostics">
              <div className="diagnostic-lead"><span className={`analysis-indicator ${isLive && !session.stalled && (isDemo || metrics.fps > 0) ? 'is-good' : ''}`} aria-hidden="true" /><div><span>Scene analysis</span><strong data-testid="model-status">{analysisLabel}</strong></div></div>
              <dl>
                <div><dt>People</dt><dd>{metrics.poses}</dd></div>
                <div><dt>Objects</dt><dd>{scene.objects.length}</dd></div>
                <div><dt>Processed FPS</dt><dd data-testid="processed-fps">{isDemo ? '-' : metrics.fps || '-'}</dd></div>
                <div><dt>Pose latency</dt><dd>{isDemo ? 'Simulated' : metrics.poseMs ? `${Math.round(metrics.poseMs)} ms` : '-'}</dd></div>
              </dl>
            </section>

            <details className="settings-panel">
              <summary>Detection settings</summary>
              <div className="settings-grid pose-settings">
                <label htmlFor="pose-quality">Pose model<select id="pose-quality" aria-label="Pose model" value={vision.quality} disabled={vision.status === 'loading'} onChange={event => vision.setQuality(event.target.value as PoseQuality)}><option value="full">Full · more detail</option><option value="lite">Lite · faster</option></select><small>Reloads analysis, keeps the camera open.</small></label>
                <label htmlFor="max-poses">People limit<select id="max-poses" value={session.maxPoses} onChange={event => session.setMaxPoses(Number(event.target.value))}>{[2, 4, 6, 8].map(count => <option key={count} value={count}>{count} people</option>)}</select><small>A higher limit uses more processing time.</small></label>
                <label htmlFor="pose-confidence">Pose confidence <output>{Math.round(session.poseConfidence * 100)}%</output><input id="pose-confidence" type="range" min="0.35" max="0.7" step="0.05" value={session.poseConfidence} onChange={event => session.setPoseConfidence(Number(event.target.value))} /><small>Lower to recover weak detections; may add false poses.</small></label>
              </div>
              <p className="coverage-note">{vision.quality === 'full' ? 'Full model with up to 960 px input. Switch to Lite if motion analysis is slow.' : 'Lite model with up to 640 px input. Switch to Full for the larger landmark model.'} Both run locally.</p>
              <div className="settings-grid">
                <label htmlFor="clip-mode">Video analysis<select id="clip-mode" aria-label="Video analysis" value={session.clipMode} disabled={clipSettingsLocked} onChange={event => session.setClipMode(event.target.value as 'review' | 'realtime')}><option value="review">Review scan · wait for every sample</option><option value="realtime">Real-time playback · skip busy frames</option></select><small>{clipSettingsLocked ? 'Stop the clip before changing mode.' : 'Applies to video files only. Live cameras stay real-time.'}</small></label>
                <label htmlFor="clip-sensitivity">Video review sensitivity<select id="clip-sensitivity" aria-label="Video review sensitivity" value={session.clipSensitivity} disabled={clipSettingsLocked} onChange={event => session.setClipSensitivity(event.target.value as 'early' | 'standard')}><option value="early">Early · 2 clear arm-motion episodes</option><option value="standard">Standard · 3 clear arm-motion episodes</option></select><small>Early review can flag sparring or play. Cameras use Standard.</small></label>
              </div>
              <label className="toggle-control object-analysis-setting"><input type="checkbox" checked={session.objectAnalysisEnabled} onChange={event => session.setObjectAnalysisEnabled(event.target.checked)} data-testid="object-analysis-toggle" /><span className="toggle-track" aria-hidden="true"><span /></span>Object analysis</label>
              <p className="coverage-note">Optional. Leave off to give motion analysis more processing time.</p>
              <div className="settings-grid">
                <label htmlFor="object-confidence">Object confidence <output>{Math.round(session.confidence * 100)}%</output><input id="object-confidence" type="range" min="0.25" max="0.75" step="0.05" value={session.confidence} onChange={event => session.setConfidence(Number(event.target.value))} /></label>
                <label htmlFor="unattended-time">Unattended bag timer<select id="unattended-time" value={session.unattendedSeconds} onChange={event => session.setUnattendedSeconds(Number(event.target.value))}>{[3, 5, 10, 20].map(seconds => <option key={seconds} value={seconds}>{seconds} seconds</option>)}</select></label>
              </div>
              <div className="model-details"><span>Pose runtime <strong data-testid="runtime-delegate">{isDemo ? 'Simulated' : vision.delegates?.pose ?? 'Loading'}</strong></span><span>Landmarks <strong>33 per pose</strong></span><span>Object runtime <strong data-testid="object-runtime-delegate">{isDemo ? 'Simulated' : vision.delegates?.objects ?? 'Loading'}{!isDemo && metrics.objectMs > 0 ? ` · ${Math.round(metrics.objectMs)} ms` : ''}</strong></span></div>
              <p className="coverage-note">Lower confidence shows more objects and may add mistakes. Small, hidden, or unfamiliar objects can be missed. This model does not recognize firearms or determine whether an action is illegal.</p>
            </details>
            {vision.status === 'error' && !isLive ? <div className="notice" role="status"><span>{vision.error ?? 'The local models could not load.'}</span><button className="text-button" type="button" onClick={session.retryAnalysis}>Retry analysis</button></div> : null}
            {vision.notice && !isDemo ? <div className="notice" role="status" data-testid="runtime-notice">{vision.notice}</div> : null}
            {session.fileError && isLive ? <p className="notice" role="status">{session.fileError}</p> : null}
          </section>

          <ObservationRail
            scene={scene} active={isLive && session.playing && !session.stalled && (isDemo || vision.status === 'ready')}
            simulated={isDemo} acknowledged={acknowledged} onAcknowledge={acknowledge} onWatch={session.watch}
            showObjects={session.objectAnalysisEnabled || isDemo && ['watched', 'unattended'].includes(session.scenario)}
            conflictPanel={<ConflictPanel snapshot={session.conflict} enabled={session.conflictEnabled} active={isLive && session.playing && !session.stalled && (isDemo || vision.status === 'ready')} simulated={isDemo} onToggle={session.setConflictEnabled} />}
          />
        </div>
      </main>

      <footer className="footer"><span>Video stays on this device. No recording.</span><span>Every alert needs human review.</span></footer>
    </div>
  )
}

export default App
