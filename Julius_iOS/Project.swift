import ProjectDescription

let project = Project(
    name: "Julius",
    organizationName: "Julius AI",
    settings: .settings(
        base: [
            "SWIFT_VERSION": "6.0",
            "SWIFT_STRICT_CONCURRENCY": "complete",
            "IPHONEOS_DEPLOYMENT_TARGET": "17.0",
            "MACOSX_DEPLOYMENT_TARGET": "14.0",
            "DEVELOPMENT_TEAM": "$(DEVELOPMENT_TEAM)"
        ]
    ),
    targets: [
        // ── Thin App Shell ───────────────────────────────────────────
        .target(
            name: "JuliusApp",
            destinations: .iOS,
            product: .app,
            bundleId: "com.julius.ios",
            deploymentTargets: .iOS("17.0"),
            infoPlist: .file(path: "Info.plist"),
            sources: ["Sources/JuliusApp/**"],
            resources: ["Resources/**"],
            dependencies: [
                .target(name: "JuliusFeatures"),
                .target(name: "JuliusUI"),
                .target(name: "JuliusCore")
            ]
        ),
        
        // ── Features (Screens & Workflows) ───────────────────────────
        .target(
            name: "JuliusFeatures",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.julius.ios.features",
            deploymentTargets: .iOS("17.0"),
            sources: ["Sources/JuliusFeatures/**"],
            dependencies: [
                .target(name: "JuliusUI"),
                .target(name: "JuliusCore")
            ]
        ),
        
        // ── UI (Claude Design System & Primitives) ───────────────────
        .target(
            name: "JuliusUI",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.julius.ios.ui",
            deploymentTargets: .iOS("17.0"),
            sources: ["Sources/JuliusUI/**"],
            dependencies: [
                .target(name: "JuliusCore")
            ]
        ),
        
        // ── Core (Network, WebSocket, Models, Home Sync) ─────────────
        .target(
            name: "JuliusCore",
            destinations: .iOS,
            product: .framework,
            bundleId: "com.julius.ios.core",
            deploymentTargets: .iOS("17.0"),
            sources: ["Sources/JuliusCore/**"],
            dependencies: []
        ),
        
        // ── Tests ─────────────────────────────────────────────────────
        .target(
            name: "JuliusAppTests",
            destinations: .iOS,
            product: .unitTests,
            bundleId: "com.julius.ios.tests",
            deploymentTargets: .iOS("17.0"),
            sources: ["Tests/JuliusAppTests/**"],
            dependencies: [
                .target(name: "JuliusApp"),
                .target(name: "JuliusCore"),
                .target(name: "JuliusUI"),
                .target(name: "JuliusFeatures")
            ]
        )
    ]
)

