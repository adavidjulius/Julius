# Julius iOS — System & Environment Prerequisites

This document outlines all system, hardware, toolchain, and account prerequisites required to develop, build, test, and deploy the native **Julius iOS & iPadOS** application.

---

## 1. Host Machine & Operating System

| Component | Minimum Requirement | Recommended | Current System Status |
|---|---|---|---|
| **Hardware** | Apple Silicon (M1 or later) or Intel Core i7 | Apple Silicon M-series (M1/M2/M3/M4) | Apple Silicon (arm64) |
| **macOS Version** | macOS 14.0 (Sonoma) | macOS 15.0+ (Sequoia) | macOS 15.0+ Sequoia |
| **Free Disk Space** | 25 GB free | 50+ GB (for Xcode, simulators, SDKs) | Verified available |
| **RAM** | 16 GB | 16 GB - 32 GB | Verified available |

---

## 2. Apple Developer Toolchain

### A. Full Xcode IDE (Required for iOS Simulator & Compilation)
- **Required Version**: Xcode 15.3+ (recommended Xcode 16.0 or newer) with iOS 17.0+ SDK.
- **Current Status**: Command Line Tools installed (`/Library/Developer/CommandLineTools`).
  > [!IMPORTANT]
  > Apple Command Line Tools provide `swift` and `clang`, but compiling native iOS apps, launching iOS Simulators, and running `xcodebuild` requires the full **Xcode.app** package.
- **How to Install Xcode**:
  1. Open the **Mac App Store** and search for `Xcode`, or download directly from [Apple Developer Downloads](https://developer.apple.com/download/all/).
  2. Once installed into `/Applications/Xcode.app`, switch the active developer directory:
     ```bash
     sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
     sudo xcodebuild -license accept
     ```

### B. Swift Compiler
- **Required**: Swift 5.10 or Swift 6.0+ (Strict Concurrency enabled).
- **Current Status**: Apple Swift 6.1.2 installed (`Target: arm64-apple-macosx15.0`).

### C. iOS Simulators & Devices
- Download the **iOS 17.0+** or **iOS 18.0+** Simulator runtime via:
  ```bash
  xcodebuild -downloadPlatform iOS
  ```
  Or via Xcode: `Settings (⌘,)` → `Platforms` → `iOS`.

---

## 3. Package Managers & Build Tooling

### A. Homebrew
- **Status**: Installed at `/opt/homebrew/bin/brew`.

### B. Node.js & npm / npx
- **Status**: Installed via Homebrew (`node v26.13.0`, `npm 11.20.0`).
- Used by `npx skillfish` and web/hybrid development tooling.

### C. Tuist (Required for App Scaffolding & Xcode Workspace Generation)
- **Role**: Tuist manages the modular project architecture (`Core`, `UI`, `Features`, and thin `App` shell) without fragile `.xcodeproj` merge conflicts.
- **Install Command**:
  ```bash
  brew install --cask tuist
  # or curl -fsSL https://get.tuist.io | bash
  ```
- **Verification**:
  ```bash
  tuist version
  ```

### D. Fastlane & Bundler (For TestFlight & CI/CD Deployment)
- **Role**: Automates screenshot capture, code signing, and TestFlight uploads.
- **Install Command**:
  ```bash
  brew install fastlane
  # or gem install bundler fastlane
  ```

### E. Code Quality Tools
- **SwiftFormat**: Enforces consistent Swift formatting across modules.
  ```bash
  brew install swiftformat
  ```
- **xcbeautify**: Formats `xcodebuild` output into clean terminal logs.
  ```bash
  brew install xcbeautify
  ```

---

## 4. Apple Developer Account & Code Signing

To run the application on physical iPhones or iPads, and to deploy to TestFlight:

1. **Apple Developer Account**:
   - Free Apple ID: Supports deployment to personal physical devices (7-day provisioning).
   - Paid Apple Developer Program ($99/yr): Required for TestFlight, App Store distribution, push notifications, and team distribution.
2. **Development Team ID**:
   - 10-character alphanumeric identifier (e.g., `A1B2C3D4E5`).
   - Find via: `security find-identity -v -p codesigning` or Xcode `Settings` → `Accounts`.
3. **Bundle Identifier**:
   - Base Bundle ID: `com.julius.ios` (or your organizational identifier `com.<your-org>.julius`).
4. **App Groups & Capabilities** (Optional / Future):
   - Background fetch for study updates.
   - App Group container for sharing data with iOS Widgets.

---

## 5. Julius Backend & Network Infrastructure

The iOS app communicates with the Julius backend daemon running locally or on your workstation/server:

1. **Julius iPad / Mobile Daemon**:
   - Starts via: `python3 ipad_tui_server.py`
   - Default Port: `9111` (or configured via `JULIUS_IPAD_PORT`)
   - Endpoints provided:
     - Health check: `GET http://<host>:9111/api/health`
     - Direct Chat REST: `POST http://<host>:9111/api/chat`
     - Streaming WebSocket: `ws://<host>:9111/ws`
2. **Network Reachability**:
   - For iOS Simulator: Connects directly to `http://localhost:9111` or `ws://localhost:9111/ws`.
   - For Physical Device: Connects to workstation LAN IP (e.g., `http://192.168.1.X:9111`) or via Bonjour/mDNS (`http://julius.local:9111`).

---

## 6. One-Step Verification

Run the bundled diagnostic script to verify all prerequisites in one command:
```bash
cd Julius_iOS
chmod +x check_prerequisites.sh
./check_prerequisites.sh
```

