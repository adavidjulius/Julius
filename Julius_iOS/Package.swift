// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JuliusiOS",
    defaultLocalization: "en",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(name: "JuliusCore", targets: ["JuliusCore"]),
        .library(name: "JuliusUI", targets: ["JuliusUI"]),
        .library(name: "JuliusFeatures", targets: ["JuliusFeatures"]),
        .executable(name: "JuliusApp", targets: ["JuliusApp"])
    ],
    dependencies: [],
    targets: [
        .target(
            name: "JuliusCore",
            dependencies: [],
            path: "Sources/JuliusCore",
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .target(
            name: "JuliusUI",
            dependencies: ["JuliusCore"],
            path: "Sources/JuliusUI",
            resources: [
                .process("Resources")
            ],
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .target(
            name: "JuliusFeatures",
            dependencies: ["JuliusCore", "JuliusUI"],
            path: "Sources/JuliusFeatures",
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .executableTarget(
            name: "JuliusApp",
            dependencies: ["JuliusCore", "JuliusUI", "JuliusFeatures"],
            path: "Sources/JuliusApp",
            exclude: ["Planformaths.md"],
            swiftSettings: [
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .testTarget(
            name: "JuliusAppTests",
            dependencies: ["JuliusCore", "JuliusUI", "JuliusFeatures"],
            path: "Tests/JuliusAppTests"
        )
    ]
)
