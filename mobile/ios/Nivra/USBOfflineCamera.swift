import SwiftUI
import AVFoundation
import CoreImage
import ImageIO

final class USBOfflineCamera: NSObject, ObservableObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    @Published private(set) var running = false
    @Published private(set) var starting = false
    @Published private(set) var code = ""
    @Published private(set) var message = "Join the same Wi-Fi router as your Mac. Internet is not needed for video."
    @Published private(set) var lastMacPull: Date?
    @Published private(set) var macConnection = ""
    @Published private(set) var macConnectionFailed = false
    @Published private(set) var macNeedsSettings = false
    private var macPairing: LocalMacPairing?
    private var pairingTask: Task<Void, Never>?
    var onPairingConsumed: (() -> Void)?
    let capture = AVCaptureSession()
    private let queue = DispatchQueue(label: "work.tanishq.nivra.usb.camera", qos: .userInitiated)
    private let store = USBFrameStore()
    private lazy var server = USBHTTPServer(store: store)
    private let context = CIContext(options: [.cacheIntermediates: false])
    private var output: AVCaptureVideoDataOutput?
    private var configured = false
    private var rotationAngle: CGFloat = 90
    private var pacing = LocalFramePacer()
    private let jpegColorSpace = CGColorSpaceCreateDeviceRGB()
    private var captureKey = "" // Accessed only on the capture queue.
    private var generation = UUID() // Accessed only on the main queue.
    private var interrupted: NSObjectProtocol?

    override init() {
        super.init()
        interrupted = NotificationCenter.default.addObserver(forName: .AVCaptureSessionWasInterrupted, object: capture, queue: .main) { [weak self] _ in
            guard let self, self.running || self.starting else { return }
            self.stop(message: "Camera paused. Tap Start camera to resume.")
        }
    }
    func start(name: String, pairing: LocalMacPairing? = nil) {
        guard !running, !starting else { return }
        generation = UUID(); let generation = generation
        macPairing = pairing; macConnection = pairing == nil ? "" : "Connecting to Mac…"
        macConnectionFailed = false; macNeedsSettings = false
        starting = true; message = "Starting camera…"
        AVCaptureDevice.requestAccess(for: .video) { [weak self] allowed in
            DispatchQueue.main.async {
                guard let self, self.generation == generation, self.starting else { return }
                guard allowed else { self.stop(message: "Allow camera access in Settings, then tap Start camera."); return }
                do {
                    let clean = String(name.components(separatedBy: .controlCharacters).joined().prefix(60))
                    let key = try self.store.begin(name: clean.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Camera" : clean)
                    self.code = key; self.lastMacPull = nil
                    self.server.onReady = { [weak self] in
                        DispatchQueue.main.async {
                            guard let self, self.generation == generation, self.store.active(key) else { return }
                            self.starting = false; self.running = true
                            self.message = "Waiting for your Mac"
                            UIApplication.shared.isIdleTimerDisabled = true
                            if self.macPairing != nil { self.connectToMac() }
                        }
                    }
                    self.server.onFailure = { [weak self] in
                        DispatchQueue.main.async {
                            guard let self, self.generation == generation else { return }
                            self.stop(message: "Local connection could not start. Tap Start camera to retry.")
                        }
                    }
                    self.server.onPull = { [weak self] date in
                        DispatchQueue.main.async {
                            guard let self, self.generation == generation, self.store.active(key) else { return }
                            self.lastMacPull = date
                        }
                    }
                    self.queue.async { [weak self] in
                        guard let self, self.store.active(key) else { return }
                        do {
                            try self.configure()
                            guard self.store.active(key) else { return }
                            self.captureKey = key; self.pacing = LocalFramePacer()
                            self.capture.startRunning()
                            guard self.capture.isRunning else { throw NSError(domain: "NIVRAUSB", code: 2) }
                            self.server.start(session: key)
                        } catch {
                            DispatchQueue.main.async {
                                guard self.generation == generation else { return }
                                self.stop(message: "Camera could not start. Tap Start camera to retry.")
                            }
                        }
                    }
                } catch { self.stop(message: "Could not create a connection code. Tap Start camera to retry.") }
            }
        }
    }
    private func configure() throws {
        guard !configured else { return }
        capture.beginConfiguration(); defer { capture.commitConfiguration() }
        capture.sessionPreset = .hd1280x720
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back) else { throw NSError(domain: "NIVRAUSB", code: 3) }
        let input = try AVCaptureDeviceInput(device: device)
        guard capture.canAddInput(input) else { throw NSError(domain: "NIVRAUSB", code: 4) }
        capture.addInput(input)
        let output = AVCaptureVideoDataOutput()
        output.alwaysDiscardsLateVideoFrames = true
        let format = output.availableVideoPixelFormatTypes.contains(kCVPixelFormatType_420YpCbCr8BiPlanarFullRange)
            ? kCVPixelFormatType_420YpCbCr8BiPlanarFullRange : kCVPixelFormatType_32BGRA
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: format]
        output.setSampleBufferDelegate(self, queue: queue)
        guard capture.canAddOutput(output) else { capture.removeInput(input); throw NSError(domain: "NIVRAUSB", code: 5) }
        capture.addOutput(output); self.output = output
        if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(rotationAngle) { connection.videoRotationAngle = rotationAngle }
        if device.activeFormat.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= 30 && $0.maxFrameRate >= 30 }) {
            do {
                try device.lockForConfiguration()
                device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 30)
                device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 30)
                device.unlockForConfiguration()
            } catch { /* JPEG production remains capped even if sensor pacing is unavailable. */ }
        }
        configured = true
    }
    func rotate(to angle: CGFloat) {
        queue.async { [weak self] in
            self?.rotationAngle = angle
            guard let connection = self?.output?.connection(with: .video), connection.isVideoRotationAngleSupported(angle) else { return }
            connection.videoRotationAngle = angle
        }
    }
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        let now = ProcessInfo.processInfo.systemUptime
        guard store.active(captureKey), let buffer = CMSampleBufferGetImageBuffer(sampleBuffer), pacing.admit(now) else { return }
        autoreleasepool {
            let source = CIImage(cvPixelBuffer: buffer)
            let scale = min(1, 960 / max(source.extent.width, source.extent.height))
            let image = source.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
            let quality = CIImageRepresentationOption(rawValue: kCGImageDestinationLossyCompressionQuality as String)
            guard let jpeg = context.jpegRepresentation(of: image, colorSpace: jpegColorSpace, options: [quality: 0.6]), jpeg.count <= 1_500_000 else { return }
            let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer)) * 1000
            store.put(jpeg: jpeg, width: Int(image.extent.width.rounded()), height: Int(image.extent.height.rounded()), timestampMs: pts.isFinite && pts >= 0 ? pts : now * 1000, session: captureKey)
        }
    }
    func connectToMac() {
        guard running, let pairing = macPairing, !code.isEmpty, pairingTask == nil else { return }
        let generation = generation, code = code
        macConnection = "Connecting to Mac…"; macConnectionFailed = false; macNeedsSettings = false
        pairingTask = Task { @MainActor [weak self] in
            do {
                try await LocalMacPairingClient.connect(pairing, code: code)
                guard let self, !Task.isCancelled, self.generation == generation, self.store.active(code) else { return }
                self.macConnection = "Connected to Mac"
                self.macPairing = nil; self.pairingTask = nil
                self.onPairingConsumed?()
            } catch {
                guard let self, !Task.isCancelled, self.generation == generation, self.store.active(code) else { return }
                let failure = LocalMacPairingFailure.classify(error)
                self.macConnection = failure.localizedDescription
                self.macNeedsSettings = failure == .localNetworkDenied
                self.macConnectionFailed = true; self.pairingTask = nil
            }
        }
    }
    func stop(message: String = "Camera stopped. Tap Start camera when you are ready.") {
        generation = UUID(); pairingTask?.cancel(); pairingTask = nil; macPairing = nil
        macConnection = ""; macConnectionFailed = false; macNeedsSettings = false
        store.stop(); server.stop()
        running = false; starting = false; code = ""; lastMacPull = nil; self.message = message
        UIApplication.shared.isIdleTimerDisabled = false
        queue.async { [weak self] in
            guard let self else { return }
            self.captureKey = ""
            if self.capture.isRunning { self.capture.stopRunning() }
        }
    }
    deinit { pairingTask?.cancel(); if let interrupted { NotificationCenter.default.removeObserver(interrupted) }; server.stop(); store.stop() }
}
