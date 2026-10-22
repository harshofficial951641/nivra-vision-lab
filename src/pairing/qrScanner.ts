/** Own the stream separately from ZXing so cancellation works during decoder setup. */
export async function startQRScanner(video: HTMLVideoElement, onResult: (text: string) => void, signal: AbortSignal) {
  let stream: MediaStream | null = null
  let controls: { stop(): void } | null = null
  let stopped = false
  const stop = () => {
    stopped = true
    signal.removeEventListener('abort', stop)
    try { controls?.stop() } catch { /* Release media even if decoder cleanup fails. */ }
    stream?.getTracks().forEach(track => { try { track.stop() } catch { /* Continue releasing other tracks. */ } })
    if (stream && video.srcObject === stream) video.srcObject = null
  }
  signal.addEventListener('abort', stop, { once: true })
  try {
    const { BrowserQRCodeReader } = await import('@zxing/browser')
    if (signal.aborted || stopped) { stop(); return { stop } }
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera scanning is unavailable here. Enter the code instead.')
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
    if (signal.aborted || stopped) { stop(); return { stop } }
    const reader = new BrowserQRCodeReader(undefined, { delayBetweenScanAttempts: 180, delayBetweenScanSuccess: 500 })
    const next = await reader.decodeFromStream(stream, video, (result, _error, callbackControls) => {
      controls = callbackControls
      if (!stopped && result) onResult(result.getText())
    })
    controls = next
    if (signal.aborted || stopped) stop()
    return { stop }
  } catch (error) { stop(); throw error }
}
