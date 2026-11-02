import Foundation

public enum MessageRole: String, Codable, Sendable {
    case user
    case assistant
    case system
}

public struct ThinkingStep: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public let text: String
    public let timestamp: Date
    public let isCompleted: Bool

    public init(id: UUID = UUID(), text: String, timestamp: Date = Date(), isCompleted: Bool = true) {
        self.id = id
        self.text = text
        self.timestamp = timestamp
        self.isCompleted = isCompleted
    }
}

public struct ThinkingState: Codable, Sendable, Equatable {
    public var summary: String
    public var steps: [ThinkingStep]
    public var isThinking: Bool
    public var durationSeconds: Double

    public init(summary: String, steps: [ThinkingStep] = [], isThinking: Bool = false, durationSeconds: Double = 0.0) {
        self.summary = summary
        self.steps = steps
        self.isThinking = isThinking
        self.durationSeconds = durationSeconds
    }
}

public struct ToolExecutionState: Codable, Sendable, Equatable {
    public var action: String          // e.g. "Creating file", "Running code", "Searching web"
    public var detail: String          // e.g. "main.py" or step count
    public var isExecuting: Bool

    public init(action: String, detail: String = "", isExecuting: Bool = false) {
        self.action = action
        self.detail = detail
        self.isExecuting = isExecuting
    }
}

public struct Artifact: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public var title: String
    public var subtitle: String
    public var content: String
    public var language: String
    public var explanation: String

    public init(
        id: UUID = UUID(),
        title: String,
        subtitle: String = "Artifact",
        content: String,
        language: String = "python",
        explanation: String = ""
    ) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.content = content
        self.language = language
        self.explanation = explanation
    }
}

public struct Attachment: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public let name: String
    public let type: String            // "image/jpeg", "application/pdf", etc.
    public let base64Data: String?
    public let localPath: String?

    public init(id: UUID = UUID(), name: String, type: String, base64Data: String? = nil, localPath: String? = nil) {
        self.id = id
        self.name = name
        self.type = type
        self.base64Data = base64Data
        self.localPath = localPath
    }
}

public struct Message: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public let role: MessageRole
    public var content: String
    public let timestamp: Date
    public var thinkingState: ThinkingState?
    public var toolState: ToolExecutionState?
    public var artifact: Artifact?
    public var attachments: [Attachment]
    public var isStreaming: Bool

    public init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        thinkingState: ThinkingState? = nil,
        toolState: ToolExecutionState? = nil,
        artifact: Artifact? = nil,
        attachments: [Attachment] = [],
        isStreaming: Bool = false
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.thinkingState = thinkingState
        self.toolState = toolState
        self.artifact = artifact
        self.attachments = attachments
        self.isStreaming = isStreaming
    }
}

