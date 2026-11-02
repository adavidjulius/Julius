import Foundation

public enum EffortLevel: String, CaseIterable, Codable, Sendable {
    case low = "Low"
    case medium = "Medium"
    case high = "High"
}

public struct AIModel: Identifiable, Codable, Sendable, Equatable, Hashable {
    public let id: String
    public let name: String
    public let subtitle: String
    public let badge: String?
    public let isProRequired: Bool

    public init(id: String, name: String, subtitle: String, badge: String? = nil, isProRequired: Bool = false) {
        self.id = id
        self.name = name
        self.subtitle = subtitle
        self.badge = badge
        self.isProRequired = isProRequired
    }

    public static let sonnet = AIModel(
        id: "julius-3-5-core",
        name: "Julius 3.5 Core",
        subtitle: "High-velocity everyday coding and reasoning",
        badge: nil,
        isProRequired: false
    )

    public static let fable = AIModel(
        id: "julius-550b-ultra",
        name: "Julius 550B Ultra",
        subtitle: "Autonomous deep reasoning & complex architecture",
        badge: "Ultra",
        isProRequired: true
    )

    public static let opus = AIModel(
        id: "julius-3-5-pro",
        name: "Julius 3.5 Pro",
        subtitle: "Full-stack system engineering & tool execution",
        badge: "Pro",
        isProRequired: true
    )

    public static let haiku = AIModel(
        id: "julius-3-5-flash",
        name: "Julius 3.5 Flash",
        subtitle: "Fastest for rapid terminal dispatches",
        badge: nil,
        isProRequired: false
    )

    public static let allModels: [AIModel] = [.fable, .opus, .sonnet, .haiku]
}

public struct Session: Identifiable, Codable, Sendable, Equatable {
    public let id: UUID
    public var title: String
    public var messages: [Message]
    public var model: AIModel
    public var effort: EffortLevel
    public var isIncognito: Bool
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: UUID = UUID(),
        title: String = "New Chat",
        messages: [Message] = [],
        model: AIModel = .sonnet,
        effort: EffortLevel = .medium,
        isIncognito: Bool = false,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.messages = messages
        self.model = model
        self.effort = effort
        self.isIncognito = isIncognito
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}
