import SwiftUI
import UniformTypeIdentifiers
import JuliusCore
import JuliusUI
import JuliusFeatures

#if os(macOS)
import AppKit

public final class JuliusAppDelegate: NSObject, NSApplicationDelegate {
    public func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            for window in NSApp.windows {
                window.title = "Julius"

                // Dynamic height fitting screen visible bounds (accounting for menu bar and Dock)
                let screen = window.screen ?? NSScreen.main
                let visibleHeight = screen?.visibleFrame.height ?? 875.0
                let targetHeight = min(740.0, max(580.0, visibleHeight - 85.0))

                window.setContentSize(NSSize(width: 414, height: targetHeight))
                window.minSize = NSSize(width: 414, height: 540)
                window.maxSize = NSSize(width: 414, height: visibleHeight - 40.0)
                window.styleMask.insert([.titled, .closable, .miniaturizable, .resizable])
                window.center()
                window.makeKeyAndOrderFront(nil)
            }
        }
    }
}
#endif

@main
public struct JuliusApp: App {
    #if os(macOS)
    @NSApplicationDelegateAdaptor(JuliusAppDelegate.self) var appDelegate
    #endif

    public init() {}

    public var body: some Scene {
        WindowGroup {
            RootContentView()
                .preferredColorScheme(.dark)
        }
    }
}

public struct RootContentView: View {
    @State private var isShowingSplash: Bool = true
    @State private var isDrawerOpen: Bool = false
    @State private var isCovertOpen: Bool = false
    @State private var isVoiceModeOpen: Bool = false
    @State private var isModelSelectorOpen: Bool = false
    @State private var isAttachmentMenuOpen: Bool = false
    @State private var isCameraOpen: Bool = false
    @State private var isThinkingSummaryOpen: Bool = false
    @State private var activeArtifact: Artifact? = nil
    @State private var isArtifactExportOpen: Bool = false

    @State private var activeTab: String = "Chats"
    @State private var projects: [ProjectItem] = []

    @State private var inputText: String = ""
    @State private var pendingAttachments: [Attachment] = []
    @State private var isDropTargeted: Bool = false
    @State private var isGenerating: Bool = false
    @State private var currentModel: AIModel = .sonnet
    @State private var currentEffort: EffortLevel = .medium
    @State private var activeSession: Session? = nil
    @State private var covertSession: Session? = nil

    @State private var sessions: [Session] = []
    @State private var isMoreOptionsOpen: Bool = false

    @StateObject private var transcriber = DeviceSpeechTranscriber.shared

    private var allArtifacts: [Artifact] {
        var list: [Artifact] = []
        for session in sessions {
            for msg in session.messages {
                if let art = msg.artifact {
                    list.append(art)
                }
            }
        }
        return list
    }

    private var responsiveSheetWidth: CGFloat {
        #if os(macOS)
        return 414
        #else
        return .infinity
        #endif
    }

    public init() {}

    public var body: some View {
        ZStack {
            // ── Primary App Body ──────────────────────────────────────────────
            ZStack {
                if isShowingSplash {
                    // ── 1. Splash Screen with Pure Transparent Julius Mark & Fluid Spring ──
                    SplashScreenView()
                        .transition(.asymmetric(
                            insertion: .opacity,
                            removal: .scale(scale: 1.05).combined(with: .opacity)
                        ))
                        .zIndex(100)
                } else if isVoiceModeOpen {
                    // ── 2. Fullscreen Interactive Live Talk Mode ─────────────────
                    VoiceModeView(model: currentModel) {
                        isVoiceModeOpen = false
                    }
                    .transition(.move(edge: .bottom))
                } else if isCovertOpen {
                    // ── 3. Covert Mode (Zero-retention sandbox) ───────────────────
                    CovertChatView(
                        session: covertSession,
                        inputText: $inputText,
                        attachments: $pendingAttachments,
                        model: currentModel,
                        effort: currentEffort,
                        isRecording: transcriber.isRecording,
                        audioPower: transcriber.audioPower,
                        isGenerating: isGenerating,
                        onOpenDrawer: { isDrawerOpen = true },
                        onCloseCovert: {
                            covertSession = nil
                            isCovertOpen = false
                        },
                        onOpenAddMenu: { isAttachmentMenuOpen = true },
                        onOpenModelSelector: { isModelSelectorOpen = true },
                        onToggleVoiceRecording: toggleVoiceTranscribing,
                        onOpenVoiceMode: { isVoiceModeOpen = true },
                        onStopGeneration: { isGenerating = false },
                        onSend: handleSendMessage
                    )
                } else if activeTab == "Projects" {
                    // ── 4. Projects View ──────────────────────────────────────────
                    ProjectsView(
                        projects: $projects,
                        onOpenDrawer: { isDrawerOpen = true },
                        onSelectProject: { project in
                            let projectSession = Session(
                                title: project.name,
                                messages: [
                                    Message(
                                        role: .assistant,
                                        content: "### Project: \(project.name)\n\(project.description.isEmpty ? "Ready to organize chats and notes for this project." : project.description)\n\n* **Workspace:** Initialized\n* **Model:** \(currentModel.name)\n\nWhat would you like to build or discuss in this project?"
                                    )
                                ],
                                model: currentModel,
                                effort: currentEffort
                            )
                            sessions.insert(projectSession, at: 0)
                            activeSession = projectSession
                            activeTab = "Chats"
                        }
                    )
                } else if activeTab == "Library" || activeTab == "Code" {
                    // ── 5. Dynamic Library / Artifacts View ───────────────────────
                    LibraryView(
                        artifacts: activeTab == "Code" ? allArtifacts.filter { ["python", "swift", "javascript", "typescript", "html", "css", "json"].contains($0.language.lowercased()) } : allArtifacts,
                        onOpenDrawer: { isDrawerOpen = true },
                        onSelectArtifact: { artifact in
                            activeArtifact = artifact
                        }
                    )
                } else if let session = activeSession, !session.messages.isEmpty {
                    // ── 6. Active Chat Thread ─────────────────────────────────────
                    ChatThreadView(
                        session: session,
                        inputText: $inputText,
                        attachments: $pendingAttachments,
                        isRecording: transcriber.isRecording,
                        audioPower: transcriber.audioPower,
                        isGenerating: isGenerating,
                        onOpenDrawer: { isDrawerOpen = true },
                        onNewChat: handleNewChat,
                        onMoreOptions: { isMoreOptionsOpen = true },
                        onOpenAddMenu: { isAttachmentMenuOpen = true },
                        onOpenModelSelector: { isModelSelectorOpen = true },
                        onToggleVoiceRecording: toggleVoiceTranscribing,
                        onOpenVoiceMode: { isVoiceModeOpen = true },
                        onStopGeneration: { isGenerating = false },
                        onOpenThinkingSummary: { isThinkingSummaryOpen = true },
                        onOpenArtifact: { artifact in
                            activeArtifact = artifact
                        },
                        onDropFile: { providers in
                            handleFileDrop(providers: providers)
                        },
                        onSend: handleSendMessage
                    )
                } else {
                    // ── 7. Main Home / Welcome ────────────────────────────────────
                    MainHomeView(
                        inputText: $inputText,
                        attachments: $pendingAttachments,
                        model: currentModel,
                        effort: currentEffort,
                        isRecording: transcriber.isRecording,
                        audioPower: transcriber.audioPower,
                        onOpenDrawer: { isDrawerOpen = true },
                        onOpenCovert: { isCovertOpen = true },
                        onOpenAddMenu: { isAttachmentMenuOpen = true },
                        onOpenModelSelector: { isModelSelectorOpen = true },
                        onToggleVoiceRecording: toggleVoiceTranscribing,
                        onOpenVoiceMode: { isVoiceModeOpen = true },
                        onSend: handleSendMessage
                    )
                }
            }

            // ── Drag & Drop Overlay Feedback ──────────────────────────────────
            if isDropTargeted {
                ZStack {
                    Color.black.opacity(0.8)
                        .ignoresSafeArea()
                    RoundedRectangle(cornerRadius: JuliusTheme.radiusXl, style: .continuous)
                        .stroke(JuliusTheme.brandGold, style: StrokeStyle(lineWidth: 2, dash: [8, 6]))
                        .padding(20)

                    VStack(spacing: 14) {
                        Image(systemName: "arrow.down.doc.fill")
                            .font(.system(size: 44))
                            .foregroundColor(JuliusTheme.brandGold)
                        Text("Drop files to upload to workspace")
                            .font(JuliusTheme.sansBold(size: 16))
                            .foregroundColor(.white)
                    }
                }
                .transition(.opacity)
                .zIndex(75)
            }

            // ── Navigation Drawer Slide-Over (Leading Slide) ───────────────────
            if isDrawerOpen {
                NavigationDrawer(
                    sessions: sessions,
                    selectedSessionId: activeSession?.id,
                    activeTab: activeTab,
                    onSelectSession: { session in
                        activeSession = session
                        activeTab = "Chats"
                    },
                    onSelectTab: { tab in
                        activeTab = tab
                    },
                    onNewChat: {
                        activeTab = "Chats"
                        handleNewChat()
                    },
                    onClose: {
                        withAnimation(.spring(response: 0.35, dampingFraction: 0.86)) {
                            isDrawerOpen = false
                        }
                    }
                )
                .transition(.move(edge: .leading))
                .zIndex(90)
            }

            // ── In-Window Modal Bottom Sheets (Strictly contained within 414px window) ──
            if isAttachmentMenuOpen {
                Color.black.opacity(0.65)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                            isAttachmentMenuOpen = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(80)

                VStack {
                    Spacer()
                    AttachmentMenuSheet(
                        onCameraTap: {
                            isAttachmentMenuOpen = false
                            isCameraOpen = true
                        },
                        onPhotosTap: {
                            isAttachmentMenuOpen = false
                            pickPhotos()
                        },
                        onFilesTap: {
                            isAttachmentMenuOpen = false
                            pickFiles()
                        },
                        onClose: {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                isAttachmentMenuOpen = false
                            }
                        }
                    )
                }
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(85)
            }

            // ── Direct Camera Capture View Modal (Strictly contained within bounds) ──
            if isCameraOpen {
                Color.black.opacity(0.65)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                            isCameraOpen = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(86)

                VStack {
                    Spacer()
                    DirectCameraCaptureView(
                        onCapture: { data, filename in
                            processIncomingData(data: data, name: filename, mime: "image/jpeg")
                        },
                        onClose: {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                isCameraOpen = false
                            }
                        }
                    )
                }
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(87)
            }

            if isModelSelectorOpen {
                Color.black.opacity(0.65)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                            isModelSelectorOpen = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(80)

                VStack {
                    Spacer()
                    ModelSelectorSheet(
                        selectedModel: $currentModel,
                        selectedEffort: $currentEffort,
                        onClose: {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                isModelSelectorOpen = false
                            }
                        }
                    )
                }
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(85)
            }

            if isThinkingSummaryOpen {
                Color.black.opacity(0.65)
                    .ignoresSafeArea()
                    .onTapGesture {
                        withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                            isThinkingSummaryOpen = false
                        }
                    }
                    .transition(.opacity)
                    .zIndex(80)

                VStack {
                    Spacer()
                    ThinkingSummarySheet(
                        thinkingState: activeSession?.messages.last?.thinkingState,
                        onClose: {
                            withAnimation(.spring(response: 0.32, dampingFraction: 0.86)) {
                                isThinkingSummaryOpen = false
                            }
                        }
                    )
                }
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(85)
            }

            if let artifact = activeArtifact {
                ArtifactDetailView(
                    artifact: artifact,
                    onClose: { activeArtifact = nil },
                    onJumpToChat: { activeArtifact = nil },
                    onExport: { isArtifactExportOpen = true }
                )
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom))
                .zIndex(88)
            }

            if isArtifactExportOpen, let artifact = activeArtifact {
                Color.black.opacity(0.65)
                    .ignoresSafeArea()
                    .onTapGesture { isArtifactExportOpen = false }
                    .transition(.opacity)
                    .zIndex(89)

                VStack {
                    Spacer()
                    ArtifactExportSheet(artifact: artifact) {
                        isArtifactExportOpen = false
                    }
                }
                .frame(maxWidth: responsiveSheetWidth)
                .transition(.move(edge: .bottom).combined(with: .opacity))
                .zIndex(90)
            }
        }
        #if os(iOS)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .ignoresSafeArea(.keyboard, edges: .bottom)
        #else
        .frame(minWidth: 414, maxWidth: 414)
        .frame(maxHeight: .infinity)
        .clipped()
        #endif
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted) { providers in
            handleFileDrop(providers: providers)
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.86), value: isDrawerOpen)
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: isAttachmentMenuOpen)
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: isModelSelectorOpen)
        .animation(.spring(response: 0.32, dampingFraction: 0.86), value: isThinkingSummaryOpen)
        .background(
            Group {
                Button("") {
                    isAttachmentMenuOpen = false
                    isCameraOpen = false
                    isModelSelectorOpen = false
                    isThinkingSummaryOpen = false
                    isDrawerOpen = false
                }
                .keyboardShortcut(.escape, modifiers: [])
                Button("") { handleSendMessage() }
                    .keyboardShortcut("s", modifiers: .command)
                Button("") { addSamplePdfForTesting() }
                    .keyboardShortcut("p", modifiers: .command)
                Button("") { toggleVoiceTranscribing() }
                    .keyboardShortcut("t", modifiers: .command)
                Button("") { isDrawerOpen.toggle() }
                    .keyboardShortcut("d", modifiers: .command)
                Button("") { isAttachmentMenuOpen.toggle(); isModelSelectorOpen = false; isDrawerOpen = false }
                    .keyboardShortcut("u", modifiers: .command)
                Button("") { isCameraOpen.toggle(); isAttachmentMenuOpen = false; isModelSelectorOpen = false; isDrawerOpen = false }
                    .keyboardShortcut("c", modifiers: [.command, .shift])
                Button("") { takeCameraShotTest() }
                    .keyboardShortcut("k", modifiers: [.command, .shift])
                Button("") { populateLongTextForScrollTest() }
                    .keyboardShortcut("l", modifiers: .command)
                Button("") { isModelSelectorOpen.toggle(); isAttachmentMenuOpen = false; isDrawerOpen = false }
                    .keyboardShortcut("m", modifiers: .command)
                Button("") { isVoiceModeOpen.toggle() }
                    .keyboardShortcut("v", modifiers: [.command, .shift])
                Button("") { isCovertOpen.toggle() }
                    .keyboardShortcut("k", modifiers: .command)
                Button("") { activeSession = nil; activeTab = "Chats"; isDrawerOpen = false }
                    .keyboardShortcut("h", modifiers: .command)
                Button("") { activeTab = "Chats"; isDrawerOpen = false }
                    .keyboardShortcut("1", modifiers: .command)
                Button("") { activeTab = "Code"; isDrawerOpen = false }
                    .keyboardShortcut("2", modifiers: .command)
                Button("") { activeTab = "Projects"; isDrawerOpen = false }
                    .keyboardShortcut("3", modifiers: .command)
                Button("") { activeTab = "Library"; isDrawerOpen = false }
                    .keyboardShortcut("4", modifiers: .command)
            }
            .opacity(0)
        )
        .confirmationDialog("Conversation Options", isPresented: $isMoreOptionsOpen, titleVisibility: .visible) {
            Button("Clear Messages", role: .destructive) {
                if let currentId = activeSession?.id, let idx = sessions.firstIndex(where: { $0.id == currentId }) {
                    sessions[idx].messages.removeAll()
                    activeSession?.messages.removeAll()
                }
            }
            Button("Delete Conversation", role: .destructive) {
                if let currentId = activeSession?.id {
                    sessions.removeAll(where: { $0.id == currentId })
                    activeSession = nil
                }
            }
            Button("Copy Full Transcript") {
                if let msgs = activeSession?.messages {
                    let transcript = msgs.map { "\($0.role == .user ? "You" : "Julius"): \($0.content)" }.joined(separator: "\n\n")
                    #if os(macOS)
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(transcript, forType: .string)
                    #endif
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
                withAnimation(.easeInOut(duration: 0.35)) {
                    isShowingSplash = false
                }
            }
            JuliusBackendClient.shared.connect()
        }
    }

    private func handleFileDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                    let targetURL: URL?
                    if let url = item as? URL {
                        targetURL = url
                    } else if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
                        targetURL = url
                    } else {
                        targetURL = nil
                    }
                    if let validURL = targetURL {
                        Task { @MainActor in
                            self.processIncomingFile(url: validURL)
                        }
                    }
                }
            }
        }
        return true
    }

    private func pickFiles() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.title = "Select Document or Code File"
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = true
        if panel.runModal() == .OK {
            for url in panel.urls {
                processIncomingFile(url: url)
            }
        }
        #endif
    }

    private func pickPhotos() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.title = "Select Photo / Image"
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.image]
        if panel.runModal() == .OK {
            for url in panel.urls {
                processIncomingFile(url: url)
            }
        }
        #endif
    }

    private func processIncomingFile(url: URL) {
        guard let data = try? Data(contentsOf: url) else { return }
        let name = url.lastPathComponent
        let ext = url.pathExtension.lowercased()
        let mime: String
        switch ext {
        case "pdf": mime = "application/pdf"
        case "jpg", "jpeg": mime = "image/jpeg"
        case "png": mime = "image/png"
        case "py": mime = "text/x-python"
        case "swift": mime = "text/x-swift"
        case "json": mime = "application/json"
        case "txt", "md": mime = "text/plain"
        default: mime = "application/octet-stream"
        }
        processIncomingData(data: data, name: name, mime: mime)
    }

    private func processIncomingData(data: Data, name: String, mime: String) {
        Task {
            do {
                let savedPath = try await CloudStorageManager.shared.uploadWorkspaceFile(name: name, data: data)
                await MainActor.run {
                    let attachment = Attachment(
                        name: name,
                        type: mime,
                        base64Data: data.count < 5_000_000 ? data.base64EncodedString() : nil,
                        localPath: savedPath
                    )
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                        self.pendingAttachments.append(attachment)
                    }
                }
            } catch {
                print("Failed to save workspace file: \(error)")
            }
        }
    }

    private func addSamplePdfForTesting() {
        let sampleData = "%PDF-1.4 Mock document for Julius engineering workspace".data(using: .utf8)!
        Task {
            let path = try? await CloudStorageManager.shared.uploadWorkspaceFile(name: "Engineering_Physics_Summary.pdf", data: sampleData)
            await MainActor.run {
                let att = Attachment(
                    name: "Engineering_Physics_Summary.pdf",
                    type: "application/pdf",
                    base64Data: sampleData.base64EncodedString(),
                    localPath: path
                )
                withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) {
                    self.pendingAttachments.append(att)
                }
            }
        }
    }

    private func takeCameraShotTest() {
        let controller = CameraCaptureController()
        controller.captureSnapshot { data in
            if let d = data {
                Task { @MainActor in
                    self.processIncomingData(data: d, name: "Direct_Camera_Shot_\(Int(Date().timeIntervalSince1970)).jpg", mime: "image/jpeg")
                }
            }
        }
    }

    private func populateLongTextForScrollTest() {
        self.inputText = """
        1. Multi-line prompt line 1: Analyzing aerodynamic drag coefficient.
        2. Multi-line prompt line 2: Computing Reynolds number at 10,000m altitude.
        3. Multi-line prompt line 3: Boundary layer transition calculations.
        4. Multi-line prompt line 4: Evaluating Navier-Stokes discretization scheme.
        5. Multi-line prompt line 5: Mesh convergence analysis on boundary walls.
        6. Multi-line prompt line 6: Verifying total pressure recovery ratio.
        7. Multi-line prompt line 7: Assessing turbulence model k-epsilon vs k-omega SST.
        8. Multi-line prompt line 8: Output formatted comparison table with LaTeX formulas.
        """
    }

    private func toggleVoiceTranscribing() {
        if transcriber.isRecording {
            transcriber.stopTranscribing()
        } else {
            transcriber.startTranscribing(
                onPartial: { partial in
                    Task { @MainActor in
                        self.inputText = partial
                    }
                },
                onComplete: { finalSpoken in
                    Task { @MainActor in
                        if !finalSpoken.isEmpty {
                            self.inputText = finalSpoken
                        }
                    }
                }
            )
        }
    }

    private func handleNewChat() {
        activeSession = Session(
            title: "New Chat",
            messages: [],
            model: currentModel,
            effort: currentEffort
        )
        inputText = ""
        pendingAttachments.removeAll()
    }

    private func handleSendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty || !pendingAttachments.isEmpty else { return }

        let attachmentsToSend = pendingAttachments
        pendingAttachments.removeAll()
        inputText = ""
        isGenerating = true

        var promptToSend = text
        if !attachmentsToSend.isEmpty {
            let filesNotice = attachmentsToSend.map { "Attached file in workspace: \($0.name) (path: \($0.localPath ?? $0.name))" }.joined(separator: "\n")
            if promptToSend.isEmpty {
                promptToSend = filesNotice
            } else {
                promptToSend = "\(promptToSend)\n\n\(filesNotice)"
            }
        }

        if isCovertOpen {
            if covertSession == nil {
                covertSession = Session(title: "Covert Chat", messages: [], model: currentModel, effort: currentEffort, isIncognito: true)
            }
            let userMsg = Message(role: .user, content: text, attachments: attachmentsToSend)
            covertSession?.messages.append(userMsg)

            let assistantMsgId = UUID()
            let placeholder = Message(
                id: assistantMsgId,
                role: .assistant,
                content: "",
                thinkingState: ThinkingState(
                    summary: "Autonomous Covert Reasoning...",
                    steps: [
                        ThinkingStep(text: "Sandboxed Zero-Retention Execution", isCompleted: true)
                    ],
                    isThinking: true,
                    durationSeconds: 0.5
                ),
                toolState: ToolExecutionState(
                    action: "Ran 2 steps · 0.4s",
                    detail: "JuliusCovert.sandbox",
                    isExecuting: false
                ),
                isStreaming: true
            )
            covertSession?.messages.append(placeholder)

            let covertHistory: [Message] = covertSession?.messages.filter { $0.id != assistantMsgId && $0.id != userMsg.id } ?? []

            Task {
                await JuliusBackendClient.shared.sendMessage(
                    prompt: promptToSend,
                    history: covertHistory,
                    model: currentModel,
                    effort: currentEffort,
                    attachments: attachmentsToSend,
                    onThinkingUpdate: { thinking in
                        DispatchQueue.main.async {
                            guard let active = covertSession,
                                  let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                            covertSession?.messages[idx].thinkingState = thinking
                        }
                    },
                    onToolUpdate: { tool in
                        DispatchQueue.main.async {
                            guard let active = covertSession,
                                  let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                            covertSession?.messages[idx].toolState = tool
                        }
                    },
                    onChunk: { chunk in
                        DispatchQueue.main.async {
                            guard let active = covertSession,
                                  let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                            covertSession?.messages[idx].content = chunk
                        }
                    },
                    onArtifact: { _ in },
                    onComplete: { completedMsg in
                        DispatchQueue.main.async {
                            defer { self.isGenerating = false }
                            guard let active = covertSession,
                                  let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                            covertSession?.messages[idx] = completedMsg
                        }
                    }
                )
            }
            return
        }

        if activeSession == nil {
            handleNewChat()
        }

        let userMsg = Message(role: .user, content: text, attachments: attachmentsToSend)
        activeSession?.messages.append(userMsg)

        // Title first message if new
        if activeSession?.messages.count == 1 {
            let titleText = !text.isEmpty ? text : (attachmentsToSend.first?.name ?? "Document")
            let truncated = String(titleText.prefix(28)) + (titleText.count > 28 ? "..." : "")
            activeSession?.title = truncated
            if let session = activeSession {
                sessions.insert(session, at: 0)
            }
        }

        // Assistant placeholder
        let assistantMsgId = UUID()
        let placeholder = Message(
            id: assistantMsgId,
            role: .assistant,
            content: "",
            thinkingState: ThinkingState(
                summary: "Autonomous Reasoning...",
                steps: [
                    ThinkingStep(text: "Inspecting Julius Workspace AST", isCompleted: true),
                    ThinkingStep(text: "Synthesizing Swift & TypeScript Modules", isCompleted: true)
                ],
                isThinking: true,
                durationSeconds: 0.8
            ),
            toolState: ToolExecutionState(
                action: "Ran 4 steps · 1.2s",
                detail: "JuliusBackend.dispatch",
                isExecuting: false
            ),
            isStreaming: true
        )
        activeSession?.messages.append(placeholder)

        let conversationHistory: [Message] = activeSession?.messages.filter { $0.id != assistantMsgId && $0.id != userMsg.id } ?? []

        // Safety watchdog: ensure isGenerating resets even if an unexpected network stall occurs
        Task {
            try? await Task.sleep(nanoseconds: 30_000_000_000)
            await MainActor.run {
                if self.isGenerating {
                    self.isGenerating = false
                }
            }
        }

        // Stream from Julius Backend API with continuous conversation context
        Task {
            await JuliusBackendClient.shared.sendMessage(
                prompt: promptToSend,
                history: conversationHistory,
                model: currentModel,
                effort: currentEffort,
                attachments: attachmentsToSend,
                onThinkingUpdate: { thinking in
                    DispatchQueue.main.async {
                        guard let active = activeSession,
                              let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                        activeSession?.messages[idx].thinkingState = thinking
                    }
                },
                onToolUpdate: { tool in
                    DispatchQueue.main.async {
                        guard let active = activeSession,
                              let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                        activeSession?.messages[idx].toolState = tool
                    }
                },
                onChunk: { chunk in
                    DispatchQueue.main.async {
                        guard let active = activeSession,
                              let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                        activeSession?.messages[idx].content = chunk
                    }
                },
                onArtifact: { art in
                    DispatchQueue.main.async {
                        guard let active = activeSession,
                              let idx = active.messages.firstIndex(where: { $0.id == assistantMsgId }) else { return }
                        activeSession?.messages[idx].artifact = art
                        Task {
                            await CloudStorageManager.shared.syncArtifact(artifact: art)
                        }
                    }
                },
                onComplete: { completedMsg in
                    DispatchQueue.main.async {
                        defer { self.isGenerating = false }
                        if let idx = activeSession?.messages.firstIndex(where: { $0.id == assistantMsgId }) {
                            activeSession?.messages[idx] = completedMsg
                        }
                        if let session = activeSession {
                            if let sIdx = sessions.firstIndex(where: { $0.id == session.id }) {
                                sessions[sIdx] = session
                            }
                            Task {
                                await CloudStorageManager.shared.syncSessionState(session: session)
                            }
                        }
                    }
                }
            )
        }
    }
}

public struct SplashScreenView: View {
    @State private var logoScale: CGFloat = 0.8
    @State private var glowOpacity: Double = 0.0
    @State private var textOffset: CGFloat = 14
    @State private var textOpacity: Double = 0.0

    public init() {}

    public var body: some View {
        ZStack {
            JuliusTheme.bgCanvas
                .ignoresSafeArea()

            // Ambient Radiant Pulse Aura in #C8B896 & Electric Green
            RadialGradient(
                gradient: Gradient(colors: [
                    JuliusTheme.brandGold.opacity(0.18),
                    JuliusTheme.electricGreen.opacity(0.08),
                    Color.clear
                ]),
                center: .center,
                startRadius: 10,
                endRadius: 260
            )
            .opacity(glowOpacity)
            .ignoresSafeArea()

            VStack {
                Spacer()

                HStack(alignment: .center, spacing: 14) {
                    JuliusMasterMarkView(size: 46, color: JuliusTheme.electricGreen, isAnimating: true, withBadge: false)
                        .scaleEffect(logoScale)

                    Text("Julius")
                        .font(JuliusTheme.serifTitle(size: 40))
                        .foregroundColor(JuliusTheme.textPrimary)
                        .offset(y: textOffset)
                        .opacity(textOpacity)
                }

                Spacer()

                Text("LUMENAGENT")
                    .font(JuliusTheme.sansBold(size: 13))
                    .tracking(4.0)
                    .foregroundColor(JuliusTheme.brandGold)
                    .opacity(textOpacity * 0.8)
                    .padding(.bottom, 38)
            }
        }
        .onAppear {
            withAnimation(.spring(response: 0.65, dampingFraction: 0.76)) {
                logoScale = 1.0
                glowOpacity = 1.0
            }
            withAnimation(.easeOut(duration: 0.5).delay(0.15)) {
                textOffset = 0
                textOpacity = 1.0
            }
        }
    }
}
