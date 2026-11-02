import Foundation

public protocol CloudStorageProvider: Sendable {
    var providerName: String { get }
    func replicateFile(path: String, content: Data) async throws
    func readFile(path: String) async throws -> Data?
    func listFiles(directory: String) async throws -> [String]
}

public final class LocalJuliusStorageProvider: CloudStorageProvider, @unchecked Sendable {
    public let providerName: String = "JuliusHome"
    private let homeDirectory: URL

    public init() {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let juliusDir = home.appendingPathComponent(".julius")
        if !FileManager.default.fileExists(atPath: juliusDir.path) {
            try? FileManager.default.createDirectory(at: juliusDir, withIntermediateDirectories: true)
        }
        self.homeDirectory = juliusDir
    }

    public func replicateFile(path: String, content: Data) async throws {
        let destination = homeDirectory.appendingPathComponent(path)
        let parentDir = destination.deletingLastPathComponent()
        if !FileManager.default.fileExists(atPath: parentDir.path) {
            try FileManager.default.createDirectory(at: parentDir, withIntermediateDirectories: true)
        }
        try content.write(to: destination)
    }

    public func readFile(path: String) async throws -> Data? {
        let fileURL = homeDirectory.appendingPathComponent(path)
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return nil }
        return try Data(contentsOf: fileURL)
    }

    public func listFiles(directory: String) async throws -> [String] {
        let dirURL = homeDirectory.appendingPathComponent(directory)
        guard FileManager.default.fileExists(atPath: dirURL.path) else { return [] }
        return try FileManager.default.contentsOfDirectory(atPath: dirURL.path)
    }
}

public final class CloudStorageManager: @unchecked Sendable {
    public static let shared = CloudStorageManager()

    public private(set) var activeProvider: CloudStorageProvider
    private var syncListeners: [(String) -> Void] = []

    public init(provider: CloudStorageProvider = LocalJuliusStorageProvider()) {
        self.activeProvider = provider
    }

    public func switchProvider(_ provider: CloudStorageProvider) {
        self.activeProvider = provider
    }

    public func onSyncEvent(_ listener: @escaping (String) -> Void) {
        syncListeners.append(listener)
    }

    public func syncArtifact(artifact: Artifact) async {
        guard let data = artifact.content.data(using: .utf8) else { return }
        let filename = "artifacts/\(artifact.title.lowercased().replacingOccurrences(of: " ", with: "_")).\(artifact.language)"
        do {
            try await activeProvider.replicateFile(path: filename, content: data)
            notifySync("Replicated artifact '\(artifact.title)' to \(activeProvider.providerName)/\(filename)")
        } catch {
            notifySync("Failed to replicate artifact: \(error.localizedDescription)")
        }
    }

    public func uploadWorkspaceFile(name: String, data: Data) async throws -> String {
        let cleanName = name.replacingOccurrences(of: "/", with: "_")
        let relativePath = "workspace_uploads/\(cleanName)"
        try await activeProvider.replicateFile(path: relativePath, content: data)

        // Also replicate to repo workspaces/uploads/ if available
        let repoWorkspaces = URL(fileURLWithPath: "workspaces/uploads")
        if FileManager.default.fileExists(atPath: "workspaces") {
            try? FileManager.default.createDirectory(at: repoWorkspaces, withIntermediateDirectories: true)
            try? data.write(to: repoWorkspaces.appendingPathComponent(cleanName))
        }

        notifySync("Uploaded workspace file '\(cleanName)' to server storage.")
        return relativePath
    }

    public func syncSessionState(session: Session) async {
        guard let data = try? JSONEncoder().encode(session) else { return }
        let path = "sessions/\(session.id.uuidString).json"
        try? await activeProvider.replicateFile(path: path, content: data)
    }

    private func notifySync(_ message: String) {
        for listener in syncListeners {
            listener(message)
        }
    }
}

