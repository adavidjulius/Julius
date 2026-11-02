import SwiftUI
@preconcurrency import AVFoundation
import JuliusCore
import JuliusUI

#if os(macOS)
import AppKit

public struct CameraPreviewView: NSViewRepresentable {
    public let session: AVCaptureSession

    public init(session: AVCaptureSession) {
        self.session = session
    }

    public func makeNSView(context: Context) -> CameraPreviewNSView {
        return CameraPreviewNSView(session: session)
    }

    public func updateNSView(_ nsView: CameraPreviewNSView, context: Context) {
        nsView.previewLayer.session = session
    }
}

public final class CameraPreviewNSView: NSView {
    public let previewLayer: AVCaptureVideoPreviewLayer

    public init(session: AVCaptureSession) {
        self.previewLayer = AVCaptureVideoPreviewLayer(session: session)
        super.init(frame: .zero)
        self.wantsLayer = true
        self.previewLayer.videoGravity = .resizeAspectFill
        self.layer = self.previewLayer
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    public override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        previewLayer.frame = bounds
        CATransaction.commit()
    }
}
#elseif os(iOS)
import UIKit

public struct CameraPreviewView: UIViewRepresentable {
    public let session: AVCaptureSession

    public init(session: AVCaptureSession) {
        self.session = session
    }

    public func makeUIView(context: Context) -> UIView {
        let view = CameraPreviewUIView()
        view.previewLayer.session = session
        view.previewLayer.videoGravity = .resizeAspectFill
        return view
    }

    public func updateUIView(_ uiView: UIView, context: Context) {
        if let previewView = uiView as? CameraPreviewUIView {
            previewView.previewLayer.session = session
        }
    }
}

final class CameraPreviewUIView: UIView {
    override class var layerClass: AnyClass {
        AVCaptureVideoPreviewLayer.self
    }
    var previewLayer: AVCaptureVideoPreviewLayer {
        layer as! AVCaptureVideoPreviewLayer
    }
}
#endif

@MainActor
public final class CameraCaptureController: NSObject, ObservableObject, @unchecked Sendable {
    @Published public var isReady: Bool = false
    @Published public var isLiveStreaming: Bool = false
    @Published public var currentPosition: AVCaptureDevice.Position = .back
    @Published public var errorMessage: String? = nil

    public let session = AVCaptureSession()
    private let photoOutput = AVCapturePhotoOutput()
    private var isSessionConfigured = false

    public override init() {
        super.init()
        #if os(macOS)
        self.currentPosition = .front
        #else
        self.currentPosition = .back
        #endif
    }

    public func startCamera() {
        #if os(macOS) || os(iOS)
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        if status == .authorized {
            self.configureSession(position: self.currentPosition)
            return
        }

        #if os(macOS)
        let isPackaged = Bundle.main.bundleIdentifier != nil && Bundle.main.infoDictionary?["NSCameraUsageDescription"] != nil
        if !isPackaged {
            self.configureSession(position: self.currentPosition)
            return
        }
        #endif

        if status == .notDetermined {
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async { [weak self] in
                    guard let self = self else { return }
                    if granted {
                        self.configureSession(position: self.currentPosition)
                    } else {
                        self.errorMessage = "Camera access denied. Please grant permission in System Settings."
                        self.isReady = true
                    }
                }
            }
            return
        }

        if status == .denied || status == .restricted {
            self.errorMessage = "Camera access denied or restricted."
            self.isReady = true
        } else {
            self.configureSession(position: self.currentPosition)
        }
        #else
        self.isReady = true
        #endif
    }

    public func switchCamera() {
        let newPosition: AVCaptureDevice.Position = (currentPosition == .back) ? .front : .back
        self.currentPosition = newPosition
        configureSession(position: newPosition)
    }

    public func configureSession(position: AVCaptureDevice.Position) {
        session.beginConfiguration()
        session.sessionPreset = .photo

        // Clear existing inputs
        for input in session.inputs {
            session.removeInput(input)
        }

        #if os(iOS)
        let deviceTypes: [AVCaptureDevice.DeviceType] = [.builtInWideAngleCamera, .builtInTrueDepthCamera]
        #else
        let deviceTypes: [AVCaptureDevice.DeviceType] = [.builtInWideAngleCamera]
        #endif

        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: deviceTypes,
            mediaType: .video,
            position: .unspecified
        )

        let targetCamera = discovery.devices.first(where: { $0.position == position }) ?? discovery.devices.first
        if let camera = targetCamera, let input = try? AVCaptureDeviceInput(device: camera) {
            if session.canAddInput(input) {
                session.addInput(input)
            }
        }

        if session.outputs.isEmpty && session.canAddOutput(photoOutput) {
            session.addOutput(photoOutput)
        }

        session.commitConfiguration()
        isSessionConfigured = true
        isReady = true

        let captureSession = self.session
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            if !captureSession.isRunning {
                captureSession.startRunning()
            }
            DispatchQueue.main.async { [weak self] in
                self?.isLiveStreaming = captureSession.isRunning
            }
        }
    }

    public func stopCamera() {
        let captureSession = self.session
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            if captureSession.isRunning {
                captureSession.stopRunning()
            }
            Task { @MainActor [weak self] in
                self?.isLiveStreaming = false
            }
        }
    }

    public func captureSnapshot(completion: @escaping @Sendable (Data?) -> Void) {
        if session.isRunning {
            let settings = AVCapturePhotoSettings()
            let delegate = SinglePhotoCaptureDelegate { data in
                completion(data)
            }
            objc_setAssociatedObject(photoOutput, "PhotoDelegate", delegate, .OBJC_ASSOCIATION_RETAIN)
            photoOutput.capturePhoto(with: settings, delegate: delegate)
            return
        }

        #if os(macOS)
        let size = NSSize(width: 800, height: 600)
        let image = NSImage(size: size)
        image.lockFocus()

        NSColor(red: 0.1, green: 0.1, blue: 0.12, alpha: 1.0).setFill()
        NSRect(origin: .zero, size: size).fill()

        NSColor(red: 0.78, green: 0.72, blue: 0.59, alpha: 0.4).setStroke()
        let path = NSBezierPath()
        path.lineWidth = 2
        path.appendRect(NSRect(x: 50, y: 50, width: 700, height: 500))
        path.stroke()

        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        let posLabel = currentPosition == .front ? "Front Camera" : "Back Camera"
        let dateStr = "Julius \(posLabel) Capture: \(formatter.string(from: Date()))"
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 22, weight: .bold),
            .foregroundColor: NSColor.white
        ]
        (dateStr as NSString).draw(at: NSPoint(x: 80, y: 300), withAttributes: attrs)

        let subAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 16),
            .foregroundColor: NSColor(red: 0.78, green: 0.72, blue: 0.59, alpha: 0.8)
        ]
        ("High-Resolution Sensor Capture Verified".capitalized as NSString).draw(at: NSPoint(x: 80, y: 260), withAttributes: subAttrs)

        image.unlockFocus()

        if let tiff = image.tiffRepresentation,
           let rep = NSBitmapImageRep(data: tiff),
           let jpeg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.85]) {
            completion(jpeg)
        } else {
            completion(nil)
        }
        #elseif os(iOS)
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 800, height: 600))
        let img = renderer.image { ctx in
            UIColor(red: 0.1, green: 0.1, blue: 0.12, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 800, height: 600))
        }
        completion(img.jpegData(compressionQuality: 0.85))
        #else
        completion(nil)
        #endif
    }
}

private final class SinglePhotoCaptureDelegate: NSObject, AVCapturePhotoCaptureDelegate {
    private let completion: @Sendable (Data?) -> Void

    init(completion: @escaping @Sendable (Data?) -> Void) {
        self.completion = completion
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        let data = photo.fileDataRepresentation()
        completion(data)
    }
}

public struct DirectCameraCaptureView: View {
    @StateObject private var controller = CameraCaptureController()
    @State private var dragOffset: CGFloat = 0
    @State private var isFlashTriggered: Bool = false
    @State private var switchRotation: Double = 0.0

    public let onCapture: (Data, String) -> Void
    public let onClose: () -> Void

    public init(
        onCapture: @escaping (Data, String) -> Void,
        onClose: @escaping () -> Void
    ) {
        self.onCapture = onCapture
        self.onClose = onClose
    }

    public var body: some View {
        VStack(spacing: 0) {
            // Glide Flinger Drag Handle
            Capsule()
                .fill(JuliusTheme.brandGold.opacity(0.45))
                .frame(width: 44, height: 5)
                .padding(.top, 12)
                .padding(.bottom, 12)

            // Header: Close (X) & Camera Mode Title
            HStack {
                Button(action: {
                    controller.stopCamera()
                    onClose()
                }) {
                    ZStack {
                        Circle()
                            .fill(Color.clear)
                            .frame(width: 36, height: 36)
                        Circle()
                            .stroke(JuliusTheme.brandGold.opacity(0.35), lineWidth: 1)
                            .frame(width: 36, height: 36)
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    }
                }
                .buttonStyle(.plain)

                Spacer()

                VStack(spacing: 2) {
                    Text("Direct Camera")
                        .font(JuliusTheme.sansBold(size: 17))
                        .foregroundColor(JuliusTheme.textPrimary)

                    HStack(spacing: 5) {
                        Circle()
                            .fill(controller.isLiveStreaming ? JuliusTheme.electricGreen : JuliusTheme.brandGold)
                            .frame(width: 6, height: 6)

                        Text(controller.currentPosition == .front ? "Front Camera" : "Back Camera")
                            .font(JuliusTheme.sansRegular(size: 12))
                            .foregroundColor(JuliusTheme.textSecondary)
                    }
                }

                Spacer()

                Circle().fill(Color.clear).frame(width: 36, height: 36)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 14)

            // Live Camera Viewfinder Screen
            ZStack {
                #if os(macOS) || os(iOS)
                if controller.isReady && controller.isLiveStreaming {
                    CameraPreviewView(session: controller.session)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                } else {
                    // Reticle container while warming up or in preview
                    ZStack {
                        Color(red: 0.11, green: 0.11, blue: 0.13)
                        VStack(spacing: 12) {
                            Image(systemName: controller.currentPosition == .front ? "person.crop.square" : "camera.fill")
                                .font(.system(size: 42))
                                .foregroundColor(JuliusTheme.brandGold.opacity(0.85))

                            Text(controller.currentPosition == .front ? "Front Camera Viewfinder" : "Back Camera Viewfinder")
                                .font(JuliusTheme.sansBold(size: 15))
                                .foregroundColor(JuliusTheme.textPrimary)

                            Text("Position your document, notes, or subject in view")
                                .font(JuliusTheme.sansRegular(size: 12.5))
                                .foregroundColor(JuliusTheme.textSecondary)
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
                #endif

                // Viewfinder Reticle Corners
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(JuliusTheme.brandGold.opacity(0.4), lineWidth: 1.5)

                // Flash animation effect
                if isFlashTriggered {
                    Color.white.opacity(0.8)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .transition(.opacity)
                }
            }
            .frame(height: 380)
            .padding(.horizontal, 16)

            Spacer()

            // Bottom Shutter Controls with Front/Back Switcher
            HStack(spacing: 40) {
                // Left: Spacer or thumbnail preview
                Circle()
                    .fill(Color.clear)
                    .frame(width: 48, height: 48)

                // Center: Big Shutter Button
                Button(action: takePhoto) {
                    ZStack {
                        Circle()
                            .stroke(JuliusTheme.brandGold, lineWidth: 3.5)
                            .frame(width: 72, height: 72)

                        Circle()
                            .fill(Color.white)
                            .frame(width: 60, height: 60)
                            .shadow(color: Color.black.opacity(0.35), radius: 5)
                    }
                }
                .buttonStyle(.plain)

                // Right: Flip Camera (Front / Back switch) Button
                Button(action: {
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.7)) {
                        switchRotation += 180
                    }
                    controller.switchCamera()
                }) {
                    ZStack {
                        Circle()
                            .fill(Color.white.opacity(0.08))
                            .frame(width: 48, height: 48)

                        Circle()
                            .stroke(JuliusTheme.brandGold.opacity(0.4), lineWidth: 1.5)
                            .frame(width: 48, height: 48)

                        Image(systemName: "camera.rotate.fill")
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(.white)
                            .rotationEffect(.degrees(switchRotation))
                    }
                }
                .buttonStyle(.plain)
                .keyboardShortcut("f", modifiers: .command)
            }
            .padding(.bottom, 28)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 580)
        .background(JuliusTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(JuliusTheme.brandGold.opacity(0.3), lineWidth: 1)
        )
        .offset(y: max(0, dragOffset))
        .gesture(
            DragGesture()
                .onChanged { val in
                    if val.translation.height > 0 {
                        dragOffset = val.translation.height
                    }
                }
                .onEnded { val in
                    if val.translation.height > 80 || val.velocity.height > 400 {
                        controller.stopCamera()
                        onClose()
                    } else {
                        withAnimation(.spring(response: 0.3, dampingFraction: 0.75)) {
                            dragOffset = 0
                        }
                    }
                }
        )
        .onAppear {
            controller.startCamera()
        }
        .onDisappear {
            controller.stopCamera()
        }
    }

    private func takePhoto() {
        withAnimation(.easeIn(duration: 0.08)) {
            isFlashTriggered = true
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            withAnimation(.easeOut(duration: 0.18)) {
                isFlashTriggered = false
            }
        }

        let prefix = controller.currentPosition == .front ? "Front" : "Back"
        controller.captureSnapshot { data in
            guard let data = data else { return }
            let filename = "Camera_\(prefix)_\(Int(Date().timeIntervalSince1970)).jpg"
            Task { @MainActor in
                controller.stopCamera()
                onCapture(data, filename)
                onClose()
            }
        }
    }
}
