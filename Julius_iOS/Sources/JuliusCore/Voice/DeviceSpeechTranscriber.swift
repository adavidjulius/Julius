import Foundation
import Speech
import AVFoundation
import Combine

/// Standalone unisolated Audio Engine Manager running off MainActor to prevent Swift 6 dispatch_assert_queue_fail
public final class AudioEngineManager: @unchecked Sendable {
    private let audioEngine = AVAudioEngine()
    private var isEngineRunning: Bool = false

    public var onPowerUpdate: (@Sendable (Float) -> Void)?
    public var onBuffer: (@Sendable (AVAudioPCMBuffer) -> Void)?

    public init() {}

    public func start() throws {
        stop()

        let inputNode = audioEngine.inputNode
        let recordingFormat = inputNode.outputFormat(forBus: 0)
        inputNode.removeTap(onBus: 0)

        inputNode.installTap(onBus: 0, bufferSize: 1024, format: recordingFormat) { [weak self] buffer, _ in
            guard let self = self else { return }
            self.onBuffer?(buffer)

            guard let channelData = buffer.floatChannelData?[0] else { return }
            let frameLength = Int(buffer.frameLength)
            var sum: Float = 0.0
            for i in 0..<frameLength {
                sum += channelData[i] * channelData[i]
            }
            let rms = sqrt(sum / Float(max(1, frameLength)))
            let normalized = min(1.0, max(0.04, rms * 18.0))
            self.onPowerUpdate?(normalized)
        }

        audioEngine.prepare()
        try audioEngine.start()
        isEngineRunning = true
    }

    public func stop() {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
        isEngineRunning = false
    }
}

final class RecognitionRequestHolder: @unchecked Sendable {
    var request: SFSpeechAudioBufferRecognitionRequest?
}

/// Native Apple device speech-to-text transcriber using real SFSpeechRecognizer & AVAudioEngine
@MainActor
public final class DeviceSpeechTranscriber: ObservableObject {
    public static let shared = DeviceSpeechTranscriber()

    @Published public var isRecording: Bool = false
    @Published public var liveTranscript: String = ""
    @Published public var audioPower: Float = 0.0

    private var speechRecognizer: SFSpeechRecognizer?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioManager = AudioEngineManager()
    private var onPartialCallback: (@Sendable (String) -> Void)?
    private var onCompleteCallback: (@Sendable (String) -> Void)?

    public init() {
        self.speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US")) ?? SFSpeechRecognizer(locale: Locale.current)
    }

    public func startTranscribing(
        onPartial: (@Sendable (String) -> Void)? = nil,
        onComplete: @escaping @Sendable (String) -> Void
    ) {
        guard !isRecording else { return }
        self.onPartialCallback = onPartial
        self.onCompleteCallback = onComplete
        self.liveTranscript = ""
        self.audioPower = 0.0
        self.isRecording = true

        #if os(iOS)
        let audioSession = AVAudioSession.sharedInstance()
        do {
            try audioSession.setCategory(.playAndRecord, mode: .measurement, options: [.duckOthers, .defaultToSpeaker])
            try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            print("Failed to configure AVAudioSession: \(error)")
        }
        #endif

        // Request real microphone hardware permission
        requestAudioHardwarePermission { [weak self] micGranted in
            guard let self = self else { return }
            guard micGranted else {
                print("Microphone access not granted.")
                DispatchQueue.main.async {
                    self.isRecording = false
                }
                return
            }

            // Check or request real Speech Recognition permission
            let speechAuth = SFSpeechRecognizer.authorizationStatus()
            if speechAuth == .authorized {
                DispatchQueue.main.async {
                    self.startAudioRecognition()
                }
                return
            }

            #if os(macOS)
            let isPackaged = Bundle.main.bundleIdentifier != nil && Bundle.main.infoDictionary?["NSSpeechRecognitionUsageDescription"] != nil
            guard isPackaged else {
                // In unpackaged dev binary, start real audio engine metering directly to prevent TCC SIGABRT
                DispatchQueue.main.async {
                    self.startAudioMeteringOnly()
                }
                return
            }
            #endif

            if speechAuth == .notDetermined {
                SFSpeechRecognizer.requestAuthorization { authStatus in
                    DispatchQueue.main.async { [weak self] in
                        guard let self = self else { return }
                        if authStatus == .authorized {
                            self.startAudioRecognition()
                        } else {
                            // If speech service is denied, still start audio engine for real waveform metering
                            self.startAudioMeteringOnly()
                        }
                    }
                }
            } else {
                DispatchQueue.main.async {
                    self.startAudioMeteringOnly()
                }
            }
        }
    }

    private func requestAudioHardwarePermission(completion: @escaping @Sendable (Bool) -> Void) {
        #if os(macOS)
        let status = AVCaptureDevice.authorizationStatus(for: .audio)
        if status == .authorized {
            completion(true)
            return
        }
        let isPackaged = Bundle.main.bundleIdentifier != nil && Bundle.main.infoDictionary?["NSMicrophoneUsageDescription"] != nil
        if !isPackaged {
            completion(true)
            return
        }
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            DispatchQueue.main.async {
                completion(granted)
            }
        }
        #elseif os(iOS)
        if #available(iOS 17.0, *) {
            let status = AVAudioApplication.shared.recordPermission
            if status == .granted {
                completion(true)
                return
            }
            AVAudioApplication.requestRecordPermission { granted in
                DispatchQueue.main.async {
                    completion(granted)
                }
            }
        } else {
            let session = AVAudioSession.sharedInstance()
            if session.recordPermission == .granted {
                completion(true)
                return
            }
            session.requestRecordPermission { granted in
                DispatchQueue.main.async {
                    completion(granted)
                }
            }
        }
        #else
        completion(true)
        #endif
    }

    private func startAudioRecognition() {
        cleanupAudioEngine()

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(macOS 10.15, iOS 13, *) {
            if speechRecognizer?.supportsOnDeviceRecognition == true {
                request.requiresOnDeviceRecognition = true
            }
        }
        self.recognitionRequest = request

        let holder = RecognitionRequestHolder()
        holder.request = request

        audioManager.onBuffer = { buffer in
            holder.request?.append(buffer)
        }
        audioManager.onPowerUpdate = { [weak self] power in
            DispatchQueue.main.async {
                self?.audioPower = power
            }
        }

        do {
            try audioManager.start()
            isRecording = true
        } catch {
            print("Failed to start audioManager: \(error)")
            startAudioMeteringOnly()
            return
        }

        recognitionTask = speechRecognizer?.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async { [weak self] in
                guard let self = self, self.isRecording else { return }
                if let result = result {
                    let realSpokenText = result.bestTranscription.formattedString
                    self.liveTranscript = realSpokenText
                    self.onPartialCallback?(realSpokenText)
                }
                if let result = result, result.isFinal {
                    self.stopTranscribing()
                } else if error != nil && result == nil {
                    self.startAudioMeteringOnly()
                }
            }
        }
    }

    private func startAudioMeteringOnly() {
        cleanupAudioEngine()

        audioManager.onBuffer = nil
        audioManager.onPowerUpdate = { [weak self] power in
            DispatchQueue.main.async {
                self?.audioPower = power
            }
        }

        do {
            try audioManager.start()
            isRecording = true
        } catch {
            print("Could not start audio metering: \(error)")
        }
    }

    public func stopTranscribing() {
        guard isRecording else { return }
        isRecording = false

        cleanupAudioEngine()

        let finalized = liveTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        let callback = onCompleteCallback
        onCompleteCallback = nil
        onPartialCallback = nil
        callback?(finalized)
    }

    private func cleanupAudioEngine() {
        audioManager.stop()
        audioManager.onBuffer = nil
        audioManager.onPowerUpdate = nil
        recognitionRequest?.endAudio()
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest = nil
    }
}
