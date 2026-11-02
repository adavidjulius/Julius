import Testing
import Foundation
@testable import JuliusCore
@testable import JuliusUI
@testable import JuliusFeatures

@Suite("Julius iOS Production App Test Suite")
struct JuliusAppTests {

    @Test("Model and Effort Definitions")
    func testModelDefinitions() {
        #expect(AIModel.allModels.count == 4)
        #expect(AIModel.sonnet.name == "Julius 3.5 Core")
        #expect(AIModel.fable.badge == "Ultra")
        #expect(AIModel.opus.badge == "Pro")
        #expect(EffortLevel.medium.rawValue == "Medium")
    }

    @Test("Message and Artifact Serialization")
    func testMessageSerialization() throws {
        let artifact = Artifact(
            title: "Tiny Vector Memory in Python",
            subtitle: "Artifact",
            content: "def embed(): pass",
            language: "python",
            explanation: "Vector memory description"
        )

        let msg = Message(
            role: .assistant,
            content: "I built a small Python program",
            thinkingState: ThinkingState(summary: "Reasoning completed"),
            toolState: ToolExecutionState(action: "Creating file", detail: "memory.py"),
            artifact: artifact
        )

        let data = try JSONEncoder().encode(msg)
        let decoded = try JSONDecoder().decode(Message.self, from: data)

        #expect(decoded.role == .assistant)
        #expect(decoded.artifact?.title == "Tiny Vector Memory in Python")
        #expect(decoded.toolState?.action == "Creating file")
    }

    @Test("Cloud Storage Provider Replicates to Home Folder")
    func testStorageReplication() async throws {
        let provider = LocalJuliusStorageProvider()
        let testData = "print('Hello from Julius iOS')".data(using: .utf8)!
        let filename = "tests/test_replicate.py"

        try await provider.replicateFile(path: filename, content: testData)
        let readData = try await provider.readFile(path: filename)

        #expect(readData != nil)
        #expect(String(data: readData!, encoding: .utf8) == "print('Hello from Julius iOS')")
    }

    @Test("Session Lifecycle and Title Truncation")
    func testSessionLifecycle() {
        var session = Session(title: "New Chat")
        #expect(session.messages.isEmpty)
        #expect(session.model == .sonnet)

        let userMsg = Message(role: .user, content: "Create a simple python code and an artifacts")
        session.messages.append(userMsg)
        #expect(session.messages.count == 1)
    }

    @Test("Markdown Table and LaTeX Math Transliteration")
    func testMarkdownTableAndLaTeX() {
        let mathSample = "Slope is \\theta to HP, \\perp to VP, Area < True, \\phi = 45^\\circ"
        let cleaned = cleanMathLaTeX(mathSample)
        #expect(cleaned.contains("θ"))
        #expect(cleaned.contains("⊥"))
        #expect(cleaned.contains("φ"))
        #expect(cleaned.contains("°"))

        let squashedTable = "| Pos | View | | :--- | :--- | | HP | TV | | VP | FV |"
        let normalized = normalizeMarkdownTables(squashedTable)
        let lines = normalized.components(separatedBy: "\n")
        #expect(lines.count >= 4)
        #expect(lines[0].contains("Pos"))
        #expect(lines[1].contains("---"))
    }

    @Test("Sanitize Content Strips Leaked Tool Commands & Thinking")
    func testSanitizeContent() {
        let rawContent = """
        <think>Let me analyze the dataset carefully.</think>
        <tool_call>{"name": "analyze_data", "arguments": {"file": "data.csv"}}</tool_call>
        Action: run_command
        Action Input: ls -la
        Observation: file1.txt file2.txt
        Here is the final verified answer for the user:
        ```json
        {"action": "test", "detail": "internal"}
        ```
        Completed successfully!
        """
        let cleaned = JuliusBackendClient.sanitizeContent(rawContent)
        #expect(!cleaned.contains("<think>"))
        #expect(!cleaned.contains("</think>"))
        #expect(!cleaned.contains("<tool_call>"))
        #expect(!cleaned.contains("run_command"))
        #expect(!cleaned.contains("Action Input:"))
        #expect(!cleaned.contains("Observation:"))
        #expect(cleaned.contains("Here is the final verified answer for the user:"))
        #expect(cleaned.contains("Completed successfully!"))
    }

    @Test("Continuous Chat Memory Passes History")
    @MainActor
    func testContinuousChatMemory() async {
        final class ResultHolder: @unchecked Sendable {
            var content: String = ""
        }
        let holder = ResultHolder()
        let client = JuliusBackendClient()
        let pastTurn1 = Message(role: .user, content: "My name is Yathiesh.")
        let pastTurn2 = Message(role: .assistant, content: "Nice to meet you Yathiesh! How can I help?")

        await client.sendMessage(
            prompt: "What is my name?",
            history: [pastTurn1, pastTurn2],
            model: .sonnet,
            effort: .medium,
            attachments: [],
            onThinkingUpdate: { _ in },
            onToolUpdate: { _ in },
            onChunk: { chunk in
                holder.content = chunk
            },
            onArtifact: { _ in },
            onComplete: { finalMsg in
                holder.content = finalMsg.content
            }
        )

        #expect(!holder.content.isEmpty)
    }

    @Test("Direct Camera Snapshot Generation & Cloud Upload")
    @MainActor
    func testCameraSnapshotGeneration() async throws {
        let controller = CameraCaptureController()
        final class DataHolder: @unchecked Sendable {
            var data: Data?
        }
        let holder = DataHolder()

        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            controller.captureSnapshot { data in
                holder.data = data
                continuation.resume()
            }
        }

        #expect(holder.data != nil)
        #expect(holder.data!.count > 1000)

        // Verify uploading camera capture to workspace storage
        let savedPath = try await CloudStorageManager.shared.uploadWorkspaceFile(
            name: "Camera_Snapshot_Test.jpg",
            data: holder.data!
        )
        #expect(savedPath.contains("workspace_uploads"))
    }

    @Test("Camera Front and Back Switching")
    @MainActor
    func testCameraSwitching() {
        let controller = CameraCaptureController()
        let initialPos = controller.currentPosition
        controller.switchCamera()
        let switchedPos = controller.currentPosition
        #expect(switchedPos != initialPos)
        controller.switchCamera()
        #expect(controller.currentPosition == initialPos)
    }

    @Test("Math Normalizer Delimiter Standardization & Streaming Guard")
    func testMathNormalizer() {
        // 1. Convert \[ ... \] to $$ ... $$
        let bracketMath = "Here is the formula: \\[ E = mc^2 \\]"
        let normBracket = normalizeMathMarkdown(bracketMath)
        #expect(normBracket.contains("$$ E = mc^2 $$"))

        // 2. Convert \( ... \) to $ ... $
        let parenMath = "Let \\( x = 5 \\) and \\( y = 10 \\)"
        let normParen = normalizeMathMarkdown(parenMath)
        #expect(normParen.contains("$ x = 5 $"))
        #expect(normParen.contains("$ y = 10 $"))

        // 3. Catch bare \boxed{...} wrapping
        let bareBoxed = "Equation: \\boxed{P_1 + \\frac{1}{2}\\rho v_1^2 = P_2 + \\frac{1}{2}\\rho v_2^2}"
        let normBoxed = normalizeMathMarkdown(bareBoxed)
        #expect(normBoxed.contains("$$\\boxed{P_1 + \\frac{1}{2}\\rho v_1^2 = P_2 + \\frac{1}{2}\\rho v_2^2}$$"))

        // 4. Streaming Guard: Auto-close unclosed $$ during streaming
        let streamingIncomplete = "Here is Bernoulli's law:\n$$\n\\boxed{P + \\frac{1}{2}\\rho v^2 = C}"
        let normStreaming = normalizeMathMarkdown(streamingIncomplete)
        let countAfter = normStreaming.components(separatedBy: "$$").count - 1
        #expect(countAfter % 2 == 0)
        #expect(normStreaming.hasSuffix("$$"))

        // 5. Preserves already wrapped equations intact
        let properMath = "$$ \\frac{a}{b} $$"
        let normProper = normalizeMathMarkdown(properMath)
        #expect(normProper == properMath)
    }

    @Test("KaTeX HTML Template Generation & Rendering")
    func testKaTeXHTMLTemplateGeneration() throws {
        let content = """
        ### Bernoulli Equation Test
        $$
        \\boxed{P_1 + \\frac{1}{2}\\rho v_1^2 + \\rho g h_1 = P_2 + \\frac{1}{2}\\rho v_2^2 + \\rho g h_2}
        $$

        | Variable | Description |
        | :--- | :--- |
        | Dynamic | $\\frac{1}{2}\\rho v^2$ |
        """
        let html = KaTeXHTMLTemplate.buildHTML(for: content)
        #expect(html.contains("katex.renderToString"))
        #expect(html.contains("marked"))
        #expect(html.contains("table-container"))

        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("test_katex.html")
        try html.write(to: tempURL, atomically: true, encoding: .utf8)
        #expect(FileManager.default.fileExists(atPath: tempURL.path))
    }
}



