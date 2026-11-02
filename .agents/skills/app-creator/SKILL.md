---
name: app-creator
description: Creates new iOS/macOS app projects with a professional architecture using Tuist for project management, modular Swift packages (Core, UI, Features), and a thin app shell. Includes Unit, UI, and Snapshot tests, CI scripts, Fastlane configuration, SwiftFormat, and AGENTS.md/CLAUDE.md for AI agent guidance. Use when the user wants to create a new iOS app project, scaffold a new app, or set up a new Swift project with best practices.
---

# App Creator Skill

Creates production-ready iOS/macOS app projects.

## Requirements

Before creating a project, collect from the user:

1. **App Name** (required) - Display name (e.g., "My Awesome App")
2. **App Identifier** (required) - Bundle ID (e.g., "com.mycompany.myapp")

Optional parameters with defaults:
- Organization Name (defaults to App Name)
- **Development Team ID** (optional) - Apple Developer Team ID for code signing
- iOS Deployment Target (default: "17.0")
- macOS Deployment Target (default: "14.0")
- Output directory (default: current directory)

### How to Find Your Development Team ID

The Development Team ID is required for deploying to physical devices. Users can find it by:

1. **From Apple Developer Portal:**
   - Go to https://developer.apple.com/account
   - Sign in with your Apple ID
   - Look for "Membership Details" → Team ID (10-character alphanumeric, e.g., "ABCDE12345")

2. **From Xcode:**
   - Open Xcode → Settings (⌘,) → Accounts tab
   - Select your Apple ID → Click your team
   - The Team ID is shown in the details

3. **From Terminal:**
   ```bash
   # List all available signing identities and teams
   security find-identity -v -p codesigning
   ```

If the user doesn't have an Apple Developer account or doesn't know their Team ID, they can leave it empty and add it later in `Project.swift`.

## Workflow

1. Ask user for App Name and App Identifier
2. Ask user for optional Development Team ID (explain how to find it if they don't know)
3. Run the creation script: `scripts/create_app.py` with `--output` pointing to the target directory
4. Run `tuist generate` in the output directory to create the Xcode workspace
5. Show the user the README.md with manual setup steps

Note: All project files (including AGENTS.md, CLAUDE.md, Project.swift, Sources/, etc.) are created in a flat structure at the output directory root. This enables Xcode Cloud compatibility.

### Script Usage

```bash
python3 scripts/create_app.py \
  --name "My App" \
  --identifier "com.example.myapp" \
  --team-id "ABCDE12345" \
  --output "."
```

All parameters:
- `--name` / `-n` (required): App display name
- `--identifier` / `-i` (required): Bundle identifier
- `--team-id` / `-t` (optional): Apple Developer Team ID for automatic signing
- `--output` / `-o` (optional): Output directory, defaults to current directory
- `--organization` (optional): Organization name, defaults to app name
- `--ios-target` (optional): iOS deployment target, defaults to "17.0"
- `--macos-target` (optional): macOS deployment target, defaults to "14.0"

## Project Structure

The generated project uses a flat structure (all files at repository root) for Xcode Cloud compatibility:

```
{output_dir}/               # Repository root (specified by --output)
├── AGENTS.md               # AI agent instructions
├── CLAUDE.md -> AGENTS.md  # Symlink for Claude Code
├── Project.swift           # Tuist project definition
├── Tuist.swift             # Tuist configuration
├── README.md               # Setup guide with TODOs
├── .swiftformat            # Code formatting rules
├── .gitignore              # Git ignore patterns
├── Sources/
│   ├── App/                # Thin app shell (DI only)
│   │   ├── {AppName}App.swift
│   │   ├── AppDependencies.swift
│   │   └── ContentView.swift
│   ├── Core/               # Domain logic, models, protocols
│   │   └── Core.swift
│   ├── UI/                 # Reusable UI components
│   │   └── UI.swift
│   └── Features/           # Feature modules with views/viewmodels
│       └── Features.swift
├── Resources/
│   └── .gitkeep
├── Tests/
│   ├── AppTests/           # App integration tests
│   ├── AppUITests/         # End-to-end UI tests
│   ├── CoreTests/          # Core module unit tests
│   ├── UITests/            # UI component tests
│   ├── FeaturesTests/      # Feature module tests
│   └── SnapshotTests/      # Visual regression tests
├── fastlane/
│   ├── Appfile             # App Store Connect config
│   ├── Fastfile            # Lane definitions
│   ├── Deliverfile         # Deliver settings
│   ├── Pluginfile          # Fastlane plugins
│   └── metadata/
│       ├── en-US/          # App Store metadata
│       └── testflight/     # TestFlight release notes
├── scripts/ci/             # CI helper scripts
│   ├── run_tests.sh        # iOS unit tests
│   ├── run_tests_macos.sh  # macOS unit tests
│   ├── run_ui_tests.sh     # UI tests with simulator
│   ├── verify_build.sh     # iOS build verification
│   ├── verify_build_macos.sh
│   ├── verify_format.sh    # SwiftFormat check
│   ├── verify_tuist_generate.sh
│   └── deploy_testflight.sh # TestFlight deployment
└── ci_scripts/             # Xcode Cloud scripts
    └── ci_post_clone.sh    # Post-clone setup (installs Tuist, generates workspace)
```

## Architecture Principles

The generated project enforces:

1. **Thin App Shell**: App target only contains dependency injection
2. **Module Separation**: Core (logic) → UI (components) → Features (screens)
3. **Protocol-Based Dependencies**: All services have protocols for testability
4. **MVVM Pattern**: ViewModels in Features, Views use @StateObject/@ObservedObject

## Post-Creation Setup

The generated README.md includes these manual steps:

### Required Steps
- [ ] Run `tuist generate` to create workspace
- [ ] Update `DEVELOPMENT_TEAM` in `Project.swift` (if not set during creation)

### Code Signing
Automatic signing is pre-configured for all targets. Once you set your `DEVELOPMENT_TEAM`, you can deploy directly to physical devices without additional Xcode configuration.

### Optional Steps
- [ ] Set up Xcode Cloud workflow
- [ ] Create App Store Connect app record
- [ ] Configure Fastlane App Store Connect API key
- [ ] Add app icons to Resources/Assets.xcassets

## TestFlight Deployment

Deploy to TestFlight using fastlane (requires Fastlane configured with App Store Connect API key):

| Command | Description |
|---------|-------------|
| `fastlane ios beta` | Build and upload to TestFlight (bumps build number, runs tests) |
| `fastlane ios beta_quick` | Quick upload (no version bump, no tests) |
| `fastlane ios beta skip_tests:true` | Skip tests but still bump version |
| `fastlane ios bump_build` | Increment build number only |
| `fastlane ios set_version version:1.2.3` | Set marketing version |

### Changelog

Edit `fastlane/metadata/testflight/release_notes.txt` before deploying. The changelog is automatically included in TestFlight uploads.

### CI Script

Use `./scripts/ci/deploy_testflight.sh` for CI/CD pipelines:

```bash
./scripts/ci/deploy_testflight.sh              # Full deploy
./scripts/ci/deploy_testflight.sh --quick      # Quick deploy
./scripts/ci/deploy_testflight.sh --skip-tests # Skip tests
```

## Xcode Cloud Support

The project is configured for Xcode Cloud with:

1. **Flat Structure**: All project files at repository root (required for Xcode Cloud to find the workspace)
2. **Post-Clone Script**: `ci_scripts/ci_post_clone.sh` runs automatically after clone to:
   - Install Tuist via Homebrew
   - Run `tuist install` to fetch dependencies
   - Run `tuist generate` to create the Xcode workspace

### Setting Up Xcode Cloud

1. Open the project in Xcode
2. Go to **Product → Xcode Cloud → Create Workflow**
3. Sign in to App Store Connect
4. Configure your workflow (Xcode Cloud will detect the post-clone script automatically)

## Axiom Skills Reference

The AGENTS.md file references these Axiom skills for AI agents:

| Category | Skills |
|----------|--------|
| Build | `axiom:fix-build`, `axiom:optimize-build` |
| Architecture | `axiom:axiom-swiftui-architecture`, `axiom:axiom-swiftui-nav` |
| Testing | `axiom:run-tests`, `axiom:axiom-swift-testing`, `axiom:axiom-ui-testing` |
| Data | `axiom:axiom-ios-data`, `axiom:axiom-swiftdata` |
| Concurrency | `axiom:axiom-swift-concurrency`, `axiom:audit concurrency` |
| Performance | `axiom:axiom-ios-performance`, `axiom:audit swiftui-performance` |
