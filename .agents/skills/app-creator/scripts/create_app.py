#!/usr/bin/env python3
"""
App Creator Script

Creates a new iOS/macOS app project with:
- Tuist project management
- Modular architecture (Core, UI, Features)
- Unit, UI, and Snapshot tests
- CI scripts
- Fastlane configuration
- AGENTS.md for AI guidance

Usage:
    python3 create_app.py --name "My App" --identifier "com.example.myapp" --output "/path/to/projects"
"""

import argparse
import os
import re
import sys
from pathlib import Path


def sanitize_name(name: str) -> str:
    """Convert app name to valid Swift identifier."""
    # Remove non-alphanumeric chars except spaces
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    # Convert to PascalCase
    parts = clean.split()
    return ''.join(word.capitalize() for word in parts)


def create_directory_structure(base_path: Path):
    """Create the project directory structure."""
    dirs = [
        "Sources/App",
        "Sources/Core",
        "Sources/Core/Models",
        "Sources/Core/Protocols",
        "Sources/Core/Services",
        "Sources/UI",
        "Sources/UI/Components",
        "Sources/Features",
        "Resources",
        "Tests/AppTests",
        "Tests/AppUITests",
        "Tests/CoreTests",
        "Tests/UITests",
        "Tests/FeaturesTests",
        "Tests/SnapshotTests",
        "fastlane/metadata/en-US",
        "fastlane/metadata/testflight",
        "scripts/ci",
        "ci_scripts",
    ]

    for dir_path in dirs:
        (base_path / dir_path).mkdir(parents=True, exist_ok=True)

    # Create .gitkeep in Resources
    (base_path / "Resources" / ".gitkeep").touch()


def substitute_template(content: str, replacements: dict) -> str:
    """Replace placeholders in template content."""
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def get_templates() -> dict:
    """Return all template files content."""
    return {
        # Tuist configuration
        "Project.swift": '''import ProjectDescription

// MARK: - Project Configuration

let iOSDeploymentTarget = "{{IOS_DEPLOYMENT_TARGET}}"
let macOSDeploymentTarget = "{{MACOS_DEPLOYMENT_TARGET}}"

let destinations: Destinations = [.iPhone, .iPad, .mac]

// MARK: - External Dependencies

let snapshotTesting = Package.remote(
    url: "https://github.com/pointfreeco/swift-snapshot-testing",
    requirement: .upToNextMajor(from: "1.17.0")
)

let project = Project(
    name: "{{APP_NAME_SAFE}}",
    organizationName: "{{ORGANIZATION_NAME}}",
    packages: [
        snapshotTesting,
    ],
    settings: .settings(
        base: [
            "SWIFT_VERSION": "5.9",
            "IPHONEOS_DEPLOYMENT_TARGET": SettingValue.string(iOSDeploymentTarget),
            "MACOSX_DEPLOYMENT_TARGET": SettingValue.string(macOSDeploymentTarget),
            // Automatic signing for all targets
            "CODE_SIGN_STYLE": "Automatic",
            "DEVELOPMENT_TEAM": "{{TEAM_ID}}",
        ],
        configurations: [
            .debug(name: "Debug"),
            .release(name: "Release"),
        ]
    ),
    targets: [
        // MARK: - Main App Target

        .target(
            name: "{{APP_NAME_SAFE}}",
            destinations: destinations,
            product: .app,
            bundleId: "{{APP_IDENTIFIER}}",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            infoPlist: .extendingDefault(with: [
                "UILaunchScreen": [
                    "UIColorName": "",
                    "UIImageName": "",
                ],
                "CFBundleDisplayName": "{{APP_NAME}}",
                "UIRequiredDeviceCapabilities": ["arm64"],
                "UISupportedInterfaceOrientations": [
                    "UIInterfaceOrientationPortrait",
                    "UIInterfaceOrientationLandscapeLeft",
                    "UIInterfaceOrientationLandscapeRight",
                ],
                "ITSAppUsesNonExemptEncryption": false,
            ]),
            sources: ["Sources/App/**"],
            resources: ["Resources/**"],
            dependencies: [
                .target(name: "Core"),
                .target(name: "UI"),
                .target(name: "Features"),
            ]
        ),

        // MARK: - Core Module

        .target(
            name: "Core",
            destinations: destinations,
            product: .framework,
            bundleId: "{{APP_IDENTIFIER}}.core",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Sources/Core/**"],
            dependencies: []
        ),

        // MARK: - UI Module

        .target(
            name: "UI",
            destinations: destinations,
            product: .framework,
            bundleId: "{{APP_IDENTIFIER}}.ui",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Sources/UI/**"],
            dependencies: [
                .target(name: "Core"),
            ]
        ),

        // MARK: - Features Module

        .target(
            name: "Features",
            destinations: destinations,
            product: .framework,
            bundleId: "{{APP_IDENTIFIER}}.features",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Sources/Features/**"],
            dependencies: [
                .target(name: "Core"),
                .target(name: "UI"),
            ]
        ),

        // MARK: - Test Targets

        .target(
            name: "CoreTests",
            destinations: destinations,
            product: .unitTests,
            bundleId: "{{APP_IDENTIFIER}}.core.tests",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Tests/CoreTests/**"],
            dependencies: [
                .target(name: "Core"),
            ]
        ),
        .target(
            name: "UITests",
            destinations: destinations,
            product: .unitTests,
            bundleId: "{{APP_IDENTIFIER}}.ui.tests",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Tests/UITests/**"],
            dependencies: [
                .target(name: "UI"),
            ]
        ),
        .target(
            name: "FeaturesTests",
            destinations: destinations,
            product: .unitTests,
            bundleId: "{{APP_IDENTIFIER}}.features.tests",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Tests/FeaturesTests/**"],
            dependencies: [
                .target(name: "Features"),
            ]
        ),
        .target(
            name: "{{APP_NAME_SAFE}}Tests",
            destinations: destinations,
            product: .unitTests,
            bundleId: "{{APP_IDENTIFIER}}.app.tests",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Tests/AppTests/**"],
            dependencies: [
                .target(name: "{{APP_NAME_SAFE}}"),
            ]
        ),
        .target(
            name: "{{APP_NAME_SAFE}}UITests",
            destinations: .iOS,
            product: .uiTests,
            bundleId: "{{APP_IDENTIFIER}}.app.uitests",
            deploymentTargets: .iOS(iOSDeploymentTarget),
            sources: ["Tests/AppUITests/**"],
            dependencies: [
                .target(name: "{{APP_NAME_SAFE}}"),
            ]
        ),
        .target(
            name: "SnapshotTests",
            destinations: destinations,
            product: .unitTests,
            bundleId: "{{APP_IDENTIFIER}}.snapshot.tests",
            deploymentTargets: .multiplatform(iOS: iOSDeploymentTarget, macOS: macOSDeploymentTarget),
            sources: ["Tests/SnapshotTests/**"],
            dependencies: [
                .target(name: "Core"),
                .target(name: "UI"),
                .package(product: "SnapshotTesting"),
            ]
        ),
    ],
    schemes: [
        .scheme(
            name: "{{APP_NAME_SAFE}}",
            shared: true,
            buildAction: .buildAction(targets: ["{{APP_NAME_SAFE}}"]),
            testAction: .targets([
                "CoreTests",
                "UITests",
                "FeaturesTests",
                "{{APP_NAME_SAFE}}Tests",
                "{{APP_NAME_SAFE}}UITests",
                "SnapshotTests",
            ]),
            runAction: .runAction(configuration: "Debug"),
            archiveAction: .archiveAction(configuration: "Release")
        ),
        .scheme(
            name: "{{APP_NAME_SAFE}}-macOS",
            shared: true,
            buildAction: .buildAction(targets: ["{{APP_NAME_SAFE}}"]),
            testAction: .targets([
                "CoreTests",
                "UITests",
                "FeaturesTests",
                "{{APP_NAME_SAFE}}Tests",
                "SnapshotTests",
            ]),
            runAction: .runAction(configuration: "Debug"),
            archiveAction: .archiveAction(configuration: "Release")
        ),
        .scheme(
            name: "{{APP_NAME_SAFE}}-Release",
            shared: true,
            buildAction: .buildAction(targets: ["{{APP_NAME_SAFE}}"]),
            runAction: .runAction(configuration: "Release"),
            archiveAction: .archiveAction(configuration: "Release")
        ),
    ]
)
''',

        "Tuist.swift": '''import ProjectDescription

let tuist = Tuist(
    compatibleXcodeVersions: .all,
    swiftVersion: "5.9"
)
''',

        # App source files
        "Sources/App/App.swift": '''import Core
import Features
import SwiftUI

@main
struct {{APP_NAME_SAFE}}App: App {
    @StateObject private var appDependencies: AppDependencies

    init() {
        let isUITesting = CommandLine.arguments.contains("--uitesting")
        let shouldResetState = CommandLine.arguments.contains("--reset-state")

        if isUITesting, shouldResetState {
            // Clear UserDefaults for clean UI test state
            if let bundleID = Bundle.main.bundleIdentifier {
                UserDefaults.standard.removePersistentDomain(forName: bundleID)
            }
            // Clear app data directory
            let fileManager = FileManager.default
            let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let dataURL = documentsURL.appendingPathComponent("AppData", isDirectory: true)
            try? fileManager.removeItem(at: dataURL)
        }

        _appDependencies = StateObject(wrappedValue: AppDependencies())
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appDependencies)
        }
        #if os(macOS)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
        #endif
    }
}
''',

        "Sources/App/AppDependencies.swift": '''import Core
import SwiftUI

/// Main dependency container for the app.
/// This is the composition root where all dependencies are wired together.
/// The app target should only contain DI/composition code, no feature logic.
@MainActor
final class AppDependencies: ObservableObject {
    // MARK: - Services

    // TODO: Add your service dependencies here
    // Example:
    // let dataService: DataServiceProtocol

    // MARK: - Initialization

    init() {
        // TODO: Initialize your services here
        // Example:
        // self.dataService = DataService()
    }
}
''',

        "Sources/App/ContentView.swift": '''import Core
import Features
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var dependencies: AppDependencies

    var body: some View {
        NavigationStack {
            Text("Welcome to {{APP_NAME}}")
                .font(.largeTitle)
                .padding()
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppDependencies())
}
''',

        # Core module
        "Sources/Core/Core.swift": '''import Foundation

/// Core module exports
/// This module contains shared protocols, models, and services
/// used throughout the application.
public enum Core {
    public static let version = "1.0.0"
}
''',

        # UI module
        "Sources/UI/UI.swift": '''import Foundation

/// UI module exports
/// This module contains shared UI components, styles, and utilities
/// used throughout the application.
public enum UI {
    public static let version = "1.0.0"
}
''',

        # Features module
        "Sources/Features/Features.swift": '''import Foundation

/// Features module exports
/// This module contains feature-specific views and view models.
public enum Features {
    public static let version = "1.0.0"
}
''',

        # Test files
        "Tests/AppTests/AppDependenciesTests.swift": '''@testable import {{APP_NAME_SAFE}}
import XCTest

final class AppDependenciesTests: XCTestCase {
    @MainActor
    func testAppDependencies_Initializes() {
        let dependencies = AppDependencies()
        XCTAssertNotNil(dependencies)
    }
}
''',

        "Tests/CoreTests/CoreTests.swift": '''@testable import Core
import XCTest

final class CoreTests: XCTestCase {
    func testCoreVersion() {
        XCTAssertEqual(Core.version, "1.0.0")
    }
}
''',

        "Tests/UITests/UITests.swift": '''@testable import UI
import XCTest

final class UIModuleTests: XCTestCase {
    func testUIVersion() {
        XCTAssertEqual(UI.version, "1.0.0")
    }
}
''',

        "Tests/FeaturesTests/FeaturesTests.swift": '''@testable import Features
import XCTest

final class FeaturesModuleTests: XCTestCase {
    func testFeaturesVersion() {
        XCTAssertEqual(Features.version, "1.0.0")
    }
}
''',

        "Tests/AppUITests/AppUITests.swift": '''import XCTest

final class {{APP_NAME_SAFE}}UITests: XCTestCase {
    var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--reset-state"]
        app.launch()
    }

    override func tearDownWithError() throws {
        app = nil
    }

    func testAppLaunches() throws {
        // Verify the app launches successfully
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
    }
}
''',

        "Tests/SnapshotTests/SnapshotTests.swift": '''import SnapshotTesting
import SwiftUI
import XCTest

@testable import UI

final class SnapshotTests: XCTestCase {
    func testExample() throws {
        // Add snapshot tests here
        // Example:
        // let view = SomeView()
        // assertSnapshot(of: view, as: .image)
    }
}
''',

        # Configuration files
        ".swiftformat": '''# SwiftFormat configuration for {{APP_NAME_SAFE}}

# Format options
--swiftversion 5.9
--indent 4
--indentcase false
--trimwhitespace always
--stripunusedargs closure-only
--maxwidth 120
--wraparguments before-first
--wrapparameters before-first
--wrapcollections before-first
--closingparen balanced
--funcattributes prev-line
--typeattributes prev-line
--varattributes same-line

# Enabled rules
--enable isEmpty
--enable sortedSwitchCases
--enable trailingCommas
--enable wrapEnumCases
--enable wrapSwitchCases

# Disabled rules
--disable redundantSelf
--disable trailingClosures
--disable wrapMultilineStatementBraces

# Exclusions
--exclude Tuist,**/.build,**/DerivedData
''',

        ".gitignore": '''# Xcode
*.xcodeproj
*.xcworkspace
*.xcuserstate
xcuserdata/
DerivedData/
*.hmap
*.ipa
*.dSYM.zip
*.dSYM

# Tuist
Derived/

# Swift Package Manager
.build/
.swiftpm/
Package.resolved

# CocoaPods (if used)
Pods/

# Fastlane
fastlane/report.xml
fastlane/Preview.html
fastlane/screenshots/**/*.png
fastlane/test_output

# macOS
.DS_Store
.AppleDouble
.LSOverride

# IDE
.idea/
*.swp
*.swo
*~

# Secrets
*.xcconfig
!**/Secrets.xcconfig.template

# Test artifacts
/tmp/
*.xcresult
''',

        # AGENTS.md
        "AGENTS.md": '''# AGENTS.md

## Project Summary
{{APP_NAME}} is a native iOS/macOS app built with SwiftUI and a modular architecture.

## Project Structure
All project files are at the repository root (flat structure for Xcode Cloud compatibility):
- `Project.swift`, `Tuist.swift` - Tuist configuration
- `Sources/` - App, Core, UI, Features modules
- `Tests/` - Unit, UI, and Snapshot tests
- `scripts/ci/` - CI helper scripts
- `ci_scripts/` - Xcode Cloud scripts
- `fastlane/` - Deployment automation

## Architecture (high level)
- Modular app with a thin app shell and separate layers for domain logic, UI, and features.
- MVVM with dependency injection to keep business logic testable and decoupled from UI.
- Shared services and reusable UI live in dedicated modules to avoid duplication.

## Module Structure
- **App**: Thin shell containing only dependency injection and app configuration
- **Core**: Domain logic, models, protocols, and services
- **UI**: Reusable UI components and styles
- **Features**: Feature-specific views and view models

## Build & Run
- Requirements: macOS 14+, Xcode 15+, iOS 17+, Tuist 4.x, SwiftFormat, xcbeautify (optional)
- Generate workspace: `tuist generate`
- Open: `open {{APP_NAME_SAFE}}.xcworkspace`
- Build (CLI): `xcodebuild -scheme {{APP_NAME_SAFE}} -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build`
- **Code Signing**: Automatic signing is pre-configured. Set your `DEVELOPMENT_TEAM` in Project.swift if not already set.

## Unit Tests

### Running Unit Tests (iOS)
```bash
# Use the CI script
./scripts/ci/run_tests.sh

# Or direct xcodebuild
xcodebuild test \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination 'platform=iOS Simulator,name=iPhone 16 Pro' \\
    -configuration Debug \\
    CODE_SIGNING_ALLOWED=NO
```

### Running Unit Tests (macOS)
```bash
./scripts/ci/run_tests_macos.sh
```

### Test Schemes
- `CoreTests` - Core domain logic tests
- `UITests` - UI component tests
- `FeaturesTests` - Feature module tests
- `{{APP_NAME_SAFE}}Tests` - App-level tests
- `{{APP_NAME_SAFE}}UITests` - End-to-end UI tests
- `SnapshotTests` - Visual regression tests

### CI Helper Scripts
- `scripts/ci/run_tests.sh` - Run iOS unit tests
- `scripts/ci/run_tests_macos.sh` - Run macOS unit tests
- `scripts/ci/run_ui_tests.sh` - Run UI tests
- `scripts/ci/verify_build.sh` - Verify iOS build
- `scripts/ci/verify_build_macos.sh` - Verify macOS build
- `scripts/ci/verify_format.sh` - Verify code formatting
- `scripts/ci/verify_tuist_generate.sh` - Verify Tuist generation
- `scripts/ci/deploy_testflight.sh` - Deploy to TestFlight
- `ci_scripts/ci_post_clone.sh` - Xcode Cloud post-clone script (installs Tuist, generates workspace)

## Formatting
- SwiftFormat config: `.swiftformat`
- Format: `swiftformat Sources Tests`
- Lint: `swiftformat --lint Sources Tests`

## Guidance for Agents
- Keep logic in `Core` and UI in `UI`/`Features`; App target should remain thin.
- Prefer protocol-based dependencies and pure functions for testability.
- **NEVER auto-commit or push to GitHub.** Only commit and push when the user explicitly requests it.

## Axiom Skills Reference
Use these Axiom skills when working on this project:

### Build & Environment
- `/axiom:fix-build` - Diagnose and fix build failures
- `/axiom:optimize-build` - Optimize build performance

### Architecture & Patterns
- `/axiom:axiom-swiftui-architecture` - SwiftUI architecture patterns
- `/axiom:axiom-swiftui-nav` - Navigation patterns
- `/axiom:axiom-ios-ui` - UI implementation guidance

### Testing
- `/axiom:run-tests` - Run test suites
- `/axiom:axiom-swift-testing` - Swift Testing framework
- `/axiom:axiom-ui-testing` - UI testing patterns

### Data & Storage
- `/axiom:axiom-ios-data` - Data persistence patterns
- `/axiom:axiom-swiftdata` - SwiftData usage

### Concurrency
- `/axiom:axiom-swift-concurrency` - Swift concurrency patterns
- `/axiom:audit concurrency` - Audit for concurrency issues

### Performance
- `/axiom:axiom-ios-performance` - Performance optimization
- `/axiom:audit swiftui-performance` - SwiftUI performance audit

### Publishing
- `/axiom:axiom-app-store-connect-ref` - App Store Connect reference
''',

        # README.md
        "README.md": '''# {{APP_NAME}}

A native iOS/macOS app built with SwiftUI and modular architecture.

## Requirements

- macOS 14+
- Xcode 15+
- iOS 17+ / macOS 14+
- [Tuist](https://tuist.io) 4.x
- [SwiftFormat](https://github.com/nicklockwood/SwiftFormat)
- [xcbeautify](https://github.com/cpisciotta/xcbeautify) (optional, for prettier build output)

## Quick Start

1. Generate the Xcode workspace:
   ```bash
   tuist generate
   ```

2. Open the workspace:
   ```bash
   open {{APP_NAME_SAFE}}.xcworkspace
   ```

3. Build and run!

## Project Structure

All project files are at the repository root (flat structure for Xcode Cloud compatibility):

```
./                          # Repository root
├── AGENTS.md               # AI agent instructions
├── CLAUDE.md -> AGENTS.md  # Symlink for Claude Code
├── Project.swift           # Tuist project definition
├── Tuist.swift             # Tuist configuration
├── README.md               # This file
├── .swiftformat            # Code formatting rules
├── .gitignore              # Git ignore patterns
├── Sources/
│   ├── App/                # Thin app shell (DI only)
│   ├── Core/               # Domain logic, models, services
│   ├── UI/                 # Reusable UI components
│   └── Features/           # Feature modules
├── Tests/
│   ├── AppTests/           # App integration tests
│   ├── CoreTests/          # Core module tests
│   ├── UITests/            # UI component tests
│   ├── FeaturesTests/      # Feature tests
│   ├── AppUITests/         # End-to-end UI tests
│   └── SnapshotTests/      # Visual regression tests
├── fastlane/               # Deployment automation
├── scripts/ci/             # CI helper scripts
└── ci_scripts/             # Xcode Cloud scripts
    └── ci_post_clone.sh    # Post-clone setup (Tuist install + generate)
```

## Development

### Run Tests
```bash
./scripts/ci/run_tests.sh
```

### Format Code
```bash
swiftformat Sources Tests
```

### Verify Build
```bash
./scripts/ci/verify_build.sh
```

## Setup Checklist

### Required Steps
- [ ] Run `tuist generate` to create workspace
- [ ] Update `DEVELOPMENT_TEAM` in Project.swift with your Apple Developer Team ID (if not set during creation)

### Code Signing
Automatic signing is pre-configured for all targets. Once you set your `DEVELOPMENT_TEAM`, you can deploy directly to devices.

### Optional Steps
- [ ] Set up Xcode Cloud workflow in App Store Connect
- [ ] Create app record in App Store Connect
- [ ] Configure Fastlane App Store Connect API key
- [ ] Add app icons to Resources/Assets.xcassets
- [ ] Update fastlane/Appfile with your credentials

## Fastlane

### Available Lanes

#### iOS
- `fastlane ios test` - Run all unit tests
- `fastlane ios build` - Build for simulator
- `fastlane ios build_release` - Build release archive
- `fastlane ios beta` - Push to TestFlight (with version bump)
- `fastlane ios beta_quick` - Quick TestFlight upload (no version bump)
- `fastlane ios release` - Push to App Store

#### macOS
- `fastlane mac test` - Run macOS unit tests
- `fastlane mac build` - Build for macOS
- `fastlane mac build_release` - Build release archive

#### Version Management
- `fastlane ios bump_build` - Increment build number (uses latest TestFlight build + 1)
- `fastlane ios set_version version:1.2.3` - Set marketing version

### TestFlight Deployment

Deploy to TestFlight with automatic version management:

```bash
# Full deployment: run tests, bump build number, build, upload with changelog
fastlane ios beta

# Quick deploy: just build and upload (no version bump, no tests)
fastlane ios beta_quick

# Skip tests but still bump version
fastlane ios beta skip_tests:true

# Deploy to specific beta groups
fastlane ios beta groups:"Internal,Beta Testers"
```

**Changelog**: Edit `fastlane/metadata/testflight/release_notes.txt` before deploying.
The changelog will be automatically included in TestFlight.

**CI Script**: Use `./scripts/ci/deploy_testflight.sh` for CI/CD pipelines.

## Xcode Cloud

This project is configured for Xcode Cloud with a flat structure (all project files at repository root).

### Automatic Setup

The `ci_scripts/ci_post_clone.sh` script runs automatically after Xcode Cloud clones the repository:
1. Installs Tuist via Homebrew
2. Runs `tuist install` to fetch dependencies
3. Runs `tuist generate` to create the Xcode workspace

### Setting Up Xcode Cloud

1. Open your project in Xcode
2. Go to **Product → Xcode Cloud → Create Workflow**
3. Sign in to App Store Connect
4. Configure your workflow (build, test, deploy)
5. Xcode Cloud will automatically detect and run `ci_scripts/ci_post_clone.sh`

### CI Scripts Location

Xcode Cloud requires CI scripts in a `ci_scripts/` folder at the repository root:
- `ci_post_clone.sh` - Runs after clone (installs Tuist, generates workspace)
- Add `ci_pre_xcodebuild.sh` for pre-build tasks
- Add `ci_post_xcodebuild.sh` for post-build tasks

## License

Copyright © {{YEAR}} {{ORGANIZATION_NAME}}. All rights reserved.
''',

        # Fastlane files
        "fastlane/Appfile": '''app_identifier("{{APP_IDENTIFIER}}")
# apple_id("your@email.com") # Your Apple email address

# itc_team_id("123456789") # App Store Connect Team ID
# team_id("{{TEAM_ID}}") # Developer Portal Team ID

# For more information about the Appfile, see:
#     https://docs.fastlane.tools/advanced/#appfile
''',

        "fastlane/Fastfile": '''default_platform(:ios)

# Project Configuration
PROJECT_ROOT = File.expand_path("..", __dir__)
WORKSPACE_FILE = File.join(PROJECT_ROOT, "{{APP_NAME_SAFE}}.xcworkspace")
APP_SCHEME = "{{APP_NAME_SAFE}}"
APP_SCHEME_RELEASE = "{{APP_NAME_SAFE}}-Release"
MACOS_SCHEME = "{{APP_NAME_SAFE}}-macOS"
METADATA_PATH = File.join(PROJECT_ROOT, "fastlane", "metadata")
SCREENSHOTS_PATH = File.join(PROJECT_ROOT, "fastlane", "screenshots")
TESTFLIGHT_NOTES_PATH = File.join(PROJECT_ROOT, "fastlane", "metadata", "testflight", "release_notes.txt")
DEFAULT_METADATA_LOCALE = "en-US"

# Ensure Tuist workspace exists
def ensure_workspace
  unless File.exist?(WORKSPACE_FILE)
    UI.message("Generating Tuist workspace...")
    Dir.chdir(PROJECT_ROOT) do
      sh("tuist generate --no-open")
    end
  end
end

def app_store_connect_api_key_if_configured
  key_path = ENV["APP_STORE_CONNECT_API_KEY_PATH"].to_s.strip
  return nil if key_path.empty?

  unless File.exist?(key_path)
    UI.user_error!("APP_STORE_CONNECT_API_KEY_PATH points to a missing file: #{key_path}")
  end

  app_store_connect_api_key(
    key_filepath: key_path,
    duration: 1200
  )
end

# Read TestFlight changelog if available
def testflight_changelog
  return nil unless File.exist?(TESTFLIGHT_NOTES_PATH)
  content = File.read(TESTFLIGHT_NOTES_PATH).strip
  content.empty? ? nil : content
end

platform :ios do

  desc "Run all unit tests"
  lane :test do
    ensure_workspace
    run_tests(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME,
      destination: "platform=iOS Simulator,name=iPhone 16 Pro",
      result_bundle: true,
      code_coverage: true
    )
  end

  desc "Run unit tests only (no UI tests)"
  lane :test_unit do
    ensure_workspace
    run_tests(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME,
      destination: "platform=iOS Simulator,name=iPhone 16 Pro",
      only_testing: [
        "CoreTests",
        "UITests",
        "FeaturesTests",
        "{{APP_NAME_SAFE}}Tests"
      ],
      result_bundle: true,
      code_coverage: true
    )
  end

  desc "Build for iOS Simulator"
  lane :build do
    ensure_workspace
    build_app(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME,
      destination: "generic/platform=iOS Simulator",
      configuration: "Debug",
      skip_archive: true,
      skip_codesigning: true
    )
  end

  desc "Build release archive for iOS"
  lane :build_release do
    ensure_workspace
    build_app(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME_RELEASE,
      export_xcargs: "-allowProvisioningUpdates",
      configuration: "Release"
    )
  end

  # ============================================================
  # Version Management
  # ============================================================

  desc "Increment build number based on latest TestFlight build"
  lane :bump_build do
    app_store_connect_api_key_if_configured

    latest = latest_testflight_build_number(
      app_identifier: CredentialsManager::AppfileConfig.try_fetch_value(:app_identifier)
    )
    new_build = latest + 1
    UI.message("Incrementing build number: #{latest} → #{new_build}")

    increment_build_number(
      build_number: new_build,
      xcodeproj: Dir.glob("#{PROJECT_ROOT}/*.xcodeproj").first
    )
  end

  desc "Set marketing version (e.g., fastlane ios set_version version:1.2.3)"
  lane :set_version do |options|
    version = options[:version]
    UI.user_error!("Missing version parameter. Usage: fastlane ios set_version version:1.2.3") unless version

    increment_version_number(
      version_number: version,
      xcodeproj: Dir.glob("#{PROJECT_ROOT}/*.xcodeproj").first
    )
    UI.success("Version set to #{version}")
  end

  # ============================================================
  # TestFlight Deployment
  # ============================================================

  desc "Push a new beta build to TestFlight (bumps build number, builds, uploads with changelog)"
  desc "Options: skip_tests:true, bump:false, groups:'Internal,Beta Testers'"
  lane :beta do |options|
    ensure_workspace
    clean_build_artifacts
    clear_derived_data

    # Run tests unless skipped
    unless options[:skip_tests]
      test_unit
    end

    # Bump build number unless explicitly disabled
    unless options[:bump] == false
      bump_build
    end

    build_app(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME_RELEASE,
      export_xcargs: "-allowProvisioningUpdates"
    )

    # Prepare upload options
    upload_options = {}

    # Add changelog if available
    changelog = testflight_changelog
    if changelog
      upload_options[:changelog] = changelog
      UI.message("Using changelog from #{TESTFLIGHT_NOTES_PATH}")
    end

    # Add beta groups if specified
    if options[:groups]
      upload_options[:groups] = options[:groups].split(",").map(&:strip)
    end

    upload_to_testflight(upload_options)
  end

  desc "Quick TestFlight upload (no version bump, no tests - just build and upload)"
  lane :beta_quick do
    ensure_workspace
    clean_build_artifacts
    clear_derived_data

    build_app(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME_RELEASE,
      export_xcargs: "-allowProvisioningUpdates"
    )

    upload_to_testflight
  end

  # ============================================================
  # App Store Release
  # ============================================================

  desc "Push a new release build to App Store"
  lane :release do
    ensure_workspace
    clean_build_artifacts
    clear_derived_data

    build_app(
      workspace: WORKSPACE_FILE,
      scheme: APP_SCHEME_RELEASE,
      export_xcargs: "-allowProvisioningUpdates"
    )
    upload_to_app_store(
      skip_metadata: true,
      skip_screenshots: true,
      precheck_include_in_app_purchases: false
    )
  end

end

platform :mac do

  desc "Run all macOS unit tests"
  lane :test do
    ensure_workspace
    run_tests(
      workspace: WORKSPACE_FILE,
      scheme: MACOS_SCHEME,
      destination: "platform=macOS",
      only_testing: [
        "CoreTests",
        "UITests",
        "FeaturesTests",
        "{{APP_NAME_SAFE}}Tests"
      ],
      result_bundle: true,
      code_coverage: true
    )
  end

  desc "Build for macOS"
  lane :build do
    ensure_workspace
    build_app(
      workspace: WORKSPACE_FILE,
      scheme: MACOS_SCHEME,
      destination: "generic/platform=macOS",
      configuration: "Debug",
      skip_archive: true,
      skip_codesigning: true
    )
  end

  desc "Build release archive for macOS"
  lane :build_release do
    ensure_workspace
    build_app(
      workspace: WORKSPACE_FILE,
      scheme: MACOS_SCHEME,
      export_xcargs: "-allowProvisioningUpdates",
      configuration: "Release"
    )
  end

end
''',

        "fastlane/Deliverfile": '''force(true)

# This project uploads App Store metadata via the dedicated `ios metadata` lane.
# Keeping these defaults here makes `deliver` behave safely if run directly.
skip_binary_upload(true)
skip_screenshots(true)

metadata_path("./fastlane/metadata")
screenshots_path("./fastlane/screenshots")

# Avoid unexpected submission behavior in CI.
submit_for_review(false)
automatic_release(false)
''',

        "fastlane/Pluginfile": '''# Autogenerated by fastlane
#
# Ensure this file is checked in to source control!

gem 'fastlane-plugin-versioning'
''',

        "fastlane/metadata/en-US/description.txt": '''{{APP_NAME}} - Your app description here.
''',

        "fastlane/metadata/en-US/keywords.txt": '''app,ios,macos
''',

        # TestFlight metadata
        "fastlane/metadata/testflight/release_notes.txt": '''## What's New

- Bug fixes and performance improvements

## Known Issues

- None
''',

        "fastlane/metadata/testflight/what_to_test.txt": '''Please test the following:

1. App launch and basic navigation
2. Core feature functionality
3. Any areas mentioned in release notes

Report issues via TestFlight feedback or contact the development team.
''',

        # CI Scripts
        "scripts/ci/run_tests.sh": '''#!/bin/bash
# Run all unit tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Running unit tests ==="
cd "$PROJECT_ROOT"

# Generate workspace if it doesn't exist
if [ ! -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Generating workspace..."
    tuist generate --no-open
fi

# Find first available iPhone Simulator with iOS 18+
SIMULATOR_ID=""

# Try iOS 26.x first
SIMULATOR_ID=$(xcrun simctl list devices available 2>/dev/null | grep -A50 "iOS 26" | grep -E "iPhone.*(Shutdown|Booted)" | head -1 | grep -oE "[A-F0-9-]{36}" || true)

# Fall back to iOS 18.x if no iOS 26 simulator found
if [ -z "$SIMULATOR_ID" ]; then
    SIMULATOR_ID=$(xcrun simctl list devices available 2>/dev/null | grep -A50 "iOS 18" | grep -E "iPhone.*(Shutdown|Booted)" | head -1 | grep -oE "[A-F0-9-]{36}" || true)
fi

if [ -z "$SIMULATOR_ID" ]; then
    echo "No available iOS 18+ iPhone simulator found"
    echo "Using generic iOS Simulator destination"
    DESTINATION="platform=iOS Simulator,name=iPhone 16 Pro"
else
    echo "Using simulator: $SIMULATOR_ID"
    DESTINATION="platform=iOS Simulator,id=$SIMULATOR_ID"
fi

xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination "$DESTINATION" \\
    -configuration Debug \\
    test \\
    CODE_SIGNING_ALLOWED=NO \\
    | xcbeautify || xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination "$DESTINATION" \\
    -configuration Debug \\
    test \\
    CODE_SIGNING_ALLOWED=NO

if [ $? -eq 0 ]; then
    echo "All tests passed"
    exit 0
else
    echo "Tests failed"
    exit 1
fi
''',

        "scripts/ci/run_tests_macos.sh": '''#!/bin/bash
# Run macOS unit tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Running macOS unit tests ==="
cd "$PROJECT_ROOT"

# Generate workspace if it doesn't exist
if [ ! -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Generating workspace..."
    tuist generate --no-open
fi

xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}}-macOS \\
    -destination 'platform=macOS' \\
    -configuration Debug \\
    -only-testing:CoreTests \\
    -only-testing:UITests \\
    -only-testing:FeaturesTests \\
    -only-testing:{{APP_NAME_SAFE}}Tests \\
    test \\
    CODE_SIGNING_ALLOWED=NO \\
    | xcbeautify || xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}}-macOS \\
    -destination 'platform=macOS' \\
    -configuration Debug \\
    -only-testing:CoreTests \\
    -only-testing:UITests \\
    -only-testing:FeaturesTests \\
    -only-testing:{{APP_NAME_SAFE}}Tests \\
    test \\
    CODE_SIGNING_ALLOWED=NO

if [ $? -eq 0 ]; then
    echo "All macOS tests passed"
    exit 0
else
    echo "macOS tests failed"
    exit 1
fi
''',

        "scripts/ci/run_ui_tests.sh": '''#!/bin/bash
# Run UI tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Running UI tests ==="
cd "$PROJECT_ROOT"

# Generate workspace if it doesn't exist
if [ ! -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Generating workspace..."
    tuist generate --no-open
fi

# Find first available iPhone Simulator with iOS 18+
SIMULATOR_ID=""
SIMULATOR_ID=$(xcrun simctl list devices available 2>/dev/null | grep -A50 "iOS 18" | grep -E "iPhone.*(Shutdown|Booted)" | head -1 | grep -oE "[A-F0-9-]{36}" || true)

if [ -z "$SIMULATOR_ID" ]; then
    echo "Using generic iOS Simulator destination"
    DESTINATION="platform=iOS Simulator,name=iPhone 16 Pro"
else
    echo "Using simulator: $SIMULATOR_ID"
    DESTINATION="platform=iOS Simulator,id=$SIMULATOR_ID"
fi

xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination "$DESTINATION" \\
    -only-testing:{{APP_NAME_SAFE}}UITests \\
    test \\
    CODE_SIGNING_ALLOWED=NO

if [ $? -eq 0 ]; then
    echo "UI tests passed"
    exit 0
else
    echo "UI tests failed"
    exit 1
fi
''',

        "scripts/ci/verify_build.sh": '''#!/bin/bash
# Verify that the project builds for iOS simulator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Verifying iOS simulator build ==="
cd "$PROJECT_ROOT"

# Generate workspace if it doesn't exist
if [ ! -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Generating workspace..."
    tuist generate --no-open
fi

echo "Building for iOS Simulator..."
xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination 'generic/platform=iOS Simulator' \\
    -configuration Debug \\
    build \\
    CODE_SIGNING_ALLOWED=NO \\
    | xcbeautify || xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}} \\
    -destination 'generic/platform=iOS Simulator' \\
    -configuration Debug \\
    build \\
    CODE_SIGNING_ALLOWED=NO

if [ $? -eq 0 ]; then
    echo "Build succeeded for iOS Simulator"
    exit 0
else
    echo "Build failed"
    exit 1
fi
''',

        "scripts/ci/verify_build_macos.sh": '''#!/bin/bash
# Verify that the project builds for macOS

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Verifying macOS build ==="
cd "$PROJECT_ROOT"

# Generate workspace if it doesn't exist
if [ ! -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Generating workspace..."
    tuist generate --no-open
fi

echo "Building for macOS..."
xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}}-macOS \\
    -destination 'platform=macOS' \\
    -configuration Debug \\
    build \\
    CODE_SIGNING_ALLOWED=NO \\
    | xcbeautify || xcodebuild \\
    -workspace {{APP_NAME_SAFE}}.xcworkspace \\
    -scheme {{APP_NAME_SAFE}}-macOS \\
    -destination 'platform=macOS' \\
    -configuration Debug \\
    build \\
    CODE_SIGNING_ALLOWED=NO

if [ $? -eq 0 ]; then
    echo "Build succeeded for macOS"
    exit 0
else
    echo "Build failed"
    exit 1
fi
''',

        "scripts/ci/verify_format.sh": '''#!/bin/bash
# Verify that all Swift files are properly formatted

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Verifying SwiftFormat compliance ==="
cd "$PROJECT_ROOT"

# Check if .swiftformat config exists
if [ ! -f ".swiftformat" ]; then
    echo ".swiftformat configuration file not found"
    exit 1
fi

# Run swiftformat in lint mode (check only, no modifications)
echo "Running SwiftFormat lint check..."
if swiftformat Sources Tests --lint 2>&1; then
    echo "All files are properly formatted"
    exit 0
else
    echo "Formatting issues found. Run 'swiftformat Sources Tests' to fix."
    exit 1
fi
''',

        "scripts/ci/verify_tuist_generate.sh": '''#!/bin/bash
# Verify that Tuist can successfully generate the workspace

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Verifying Tuist workspace generation ==="
cd "$PROJECT_ROOT"

# Clean any existing generated files
if [ -d "*.xcworkspace" ] || [ -d "*.xcodeproj" ]; then
    echo "Cleaning existing generated files..."
    rm -rf *.xcworkspace *.xcodeproj
fi

# Generate the workspace
echo "Running 'tuist generate'..."
tuist generate --no-open

# Verify the workspace was created
if [ -d "{{APP_NAME_SAFE}}.xcworkspace" ]; then
    echo "Workspace generated successfully"
    exit 0
else
    echo "Workspace generation failed - {{APP_NAME_SAFE}}.xcworkspace not found"
    exit 1
fi
''',

        "scripts/ci/deploy_testflight.sh": '''#!/bin/bash
# Deploy to TestFlight
#
# Usage:
#   ./scripts/ci/deploy_testflight.sh              # Full deploy (bump + tests + upload)
#   ./scripts/ci/deploy_testflight.sh --quick      # Quick deploy (just build and upload)
#   ./scripts/ci/deploy_testflight.sh --skip-tests # Skip tests but bump version

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== Deploying to TestFlight ==="

# Parse arguments
LANE="beta"
LANE_OPTIONS=""

for arg in "$@"; do
    case $arg in
        --quick)
            LANE="beta_quick"
            ;;
        --skip-tests)
            LANE_OPTIONS="skip_tests:true"
            ;;
    esac
done

# Run the appropriate lane
if [ -n "$LANE_OPTIONS" ]; then
    bundle exec fastlane ios "$LANE" "$LANE_OPTIONS"
else
    bundle exec fastlane ios "$LANE"
fi

echo "=== TestFlight deployment complete ==="
''',

        # Xcode Cloud Scripts
        "ci_scripts/ci_post_clone.sh": '''#!/bin/bash
# Xcode Cloud Post-Clone Script
# This script runs automatically after Xcode Cloud clones the repository.
# It installs Tuist and generates the Xcode workspace.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Xcode Cloud Post-Clone Script ==="
cd "$PROJECT_ROOT"

# Install Tuist via Homebrew
echo "Installing Tuist..."
brew tap tuist/tuist
brew install --formula tuist

# Install dependencies and generate workspace
echo "Installing Tuist dependencies..."
tuist install

echo "Generating Xcode workspace..."
tuist generate --no-open

echo "=== Post-clone setup complete ==="
''',
    }


def create_project(
    name: str,
    identifier: str,
    output_dir: str,
    team_id: str = "",
    organization: str = "",
    ios_target: str = "17.0",
    macos_target: str = "14.0"
):
    """Create a new iOS/macOS app project."""

    name_safe = sanitize_name(name)
    org_name = organization if organization else name

    # Flat structure - all project files at root (output directory)
    root_path = Path(output_dir)
    project_path = root_path  # Flat structure - no subfolder

    # Check if key project files already exist
    key_files = [project_path / "Project.swift", project_path / "Tuist.swift"]
    if any(f.exists() for f in key_files):
        print(f"Error: Project files already exist in: {project_path}")
        sys.exit(1)

    print(f"Creating project: {name}")
    print(f"  Safe name: {name_safe}")
    print(f"  Identifier: {identifier}")
    print(f"  Project directory: {project_path.absolute()}")

    # Ensure project path exists
    project_path.mkdir(parents=True, exist_ok=True)

    # Create directory structure (flat - all at project root)
    create_directory_structure(project_path)

    # Prepare replacements
    import datetime
    replacements = {
        "APP_NAME": name,
        "APP_NAME_SAFE": name_safe,
        "APP_IDENTIFIER": identifier,
        "ORGANIZATION_NAME": org_name,
        "TEAM_ID": team_id,
        "IOS_DEPLOYMENT_TARGET": ios_target,
        "MACOS_DEPLOYMENT_TARGET": macos_target,
        "YEAR": str(datetime.datetime.now().year),
    }

    # Get templates and write files
    templates = get_templates()

    for template_path, content in templates.items():
        # Substitute placeholders
        final_content = substitute_template(content, replacements)

        # Determine target path (flat structure - all files at project root)
        if template_path == "Sources/App/App.swift":
            # Rename App.swift to {AppName}App.swift
            actual_path = project_path / f"Sources/App/{name_safe}App.swift"
        else:
            actual_path = project_path / template_path

        # Write file
        actual_path.parent.mkdir(parents=True, exist_ok=True)
        actual_path.write_text(final_content)

        # Make scripts executable (both scripts/ci and ci_scripts directories)
        if (template_path.startswith("scripts/") or template_path.startswith("ci_scripts/")) and template_path.endswith(".sh"):
            actual_path.chmod(0o755)

    # Create CLAUDE.md symlink pointing to AGENTS.md
    claude_md = project_path / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.symlink_to("AGENTS.md")

    # Create fastlane .gitkeep
    (project_path / "fastlane" / "metadata" / "en-US" / ".gitkeep").touch()

    print(f"\nProject created successfully!")
    print(f"  Project directory: {project_path.absolute()}")
    print("\nNext steps:")
    print(f"  1. cd {project_path.absolute()}")
    print("  2. tuist generate")
    print(f"  3. open {name_safe}.xcworkspace")
    print(f"\nSee README.md for the full setup checklist.")

    return project_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a new iOS/macOS app project"
    )
    parser.add_argument(
        "--name", "-n",
        required=True,
        help="App name (e.g., 'My Awesome App')"
    )
    parser.add_argument(
        "--identifier", "-i",
        required=True,
        help="Bundle identifier (e.g., 'com.example.myapp')"
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Output directory (default: current directory)"
    )
    parser.add_argument(
        "--team-id", "-t",
        default="",
        help="Development team ID (optional)"
    )
    parser.add_argument(
        "--organization",
        default="",
        help="Organization name (defaults to app name)"
    )
    parser.add_argument(
        "--ios-target",
        default="17.0",
        help="iOS deployment target (default: 17.0)"
    )
    parser.add_argument(
        "--macos-target",
        default="14.0",
        help="macOS deployment target (default: 14.0)"
    )

    args = parser.parse_args()

    create_project(
        name=args.name,
        identifier=args.identifier,
        output_dir=args.output,
        team_id=args.team_id,
        organization=args.organization,
        ios_target=args.ios_target,
        macos_target=args.macos_target
    )


if __name__ == "__main__":
    main()
