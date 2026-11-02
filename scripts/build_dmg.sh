#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Build script for Julius Agent macOS .app and .dmg
#
# Prerequisites:
#   brew install create-dmg
#   .venv/bin/pip install py2app
#
# Usage:
#   bash scripts/build_dmg.sh
# ─────────────────────────────────────────────────────────────────────

# Execute command: set -euo pipefail
set -euo pipefail

APP_NAME="Julius Agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
BUILD_DIR="$PROJECT_DIR/build"

# Print message to standard output: ╔═══════════════════════════════════════════════════╗
echo "╔═══════════════════════════════════════════════════╗"
# Print message to standard output: ║       ❄️  Julius Agent — macOS Build Script       ║
echo "║       ❄️  Julius Agent — macOS Build Script       ║"
# Print message to standard output: ╚═══════════════════════════════════════════════════╝
echo "╚═══════════════════════════════════════════════════╝"
# Print message to standard output:
echo ""

# ── Step 1: Clean previous builds ──
echo "🧹 Cleaning previous builds..."
rm -rf "$DIST_DIR" "$BUILD_DIR"
# Print message to standard output:    ✅ Clean
echo "   ✅ Clean"

# Ensure assets/icon.icns is generated from the logo
if [ ! -f "$PROJECT_DIR/assets/icon.icns" ]; then
    # Print message to standard output: 🎨 assets/icon.icns not found, generating...
    echo "🎨 assets/icon.icns not found, generating..."
    # Execute command: bash "$PROJECT_DIR/scripts/generate_icns.sh"
    bash "$PROJECT_DIR/scripts/generate_icns.sh"
# End of if-conditional control block
fi


# ── Step 2: Build .app with py2app ──
echo ""
# Print message to standard output: 📦 Building .app bundle with py2app...
echo "📦 Building .app bundle with py2app..."
cd "$PROJECT_DIR"
# Execute command: .venv/bin/python3 setup_app.py py2app --no-strip 2>&1 | tail -5
.venv/bin/python3 setup_app.py py2app --no-strip 2>&1 | tail -5
# Print message to standard output:    ✅ .app created at: $DIST_DIR/$APP_NAME.app
echo "   ✅ .app created at: $DIST_DIR/$APP_NAME.app"

# ── Step 3: Bundle Playwright browsers ──
echo ""
# Print message to standard output: 🌐 Bundling Playwright browser...
echo "🌐 Bundling Playwright browser..."

# Find the Playwright browser path
PW_BROWSER_DIR=$(.venv/bin/python3 -c "
import playwright._impl._driver as d
import os
print(os.path.join(os.path.dirname(d.__file__), 'driver', 'package', '.local-browsers'))
" 2>/dev/null || echo "")

# Evaluate condition check: -d "$PW_BROWSER_DIR" ] && [ "$(ls -A "$PW_BROWSER_DIR" 2>/dev/null)"
if [ -d "$PW_BROWSER_DIR" ] && [ "$(ls -A "$PW_BROWSER_DIR" 2>/dev/null)" ]; then
    RESOURCES_DIR="$DIST_DIR/$APP_NAME.app/Contents/Resources"
    mkdir -p "$RESOURCES_DIR/.local-browsers"
    cp -R "$PW_BROWSER_DIR/"* "$RESOURCES_DIR/.local-browsers/" 2>/dev/null || true
    # Print message to standard output:    ✅ Playwright browsers bundled from venv
    echo "   ✅ Playwright browsers bundled from venv"
# Alternative condition check: -d "$HOME/Library/Caches/ms-playwright"
elif [ -d "$HOME/Library/Caches/ms-playwright" ]; then
    RESOURCES_DIR="$DIST_DIR/$APP_NAME.app/Contents/Resources"
    mkdir -p "$RESOURCES_DIR/.local-browsers"
    cp -R "$HOME/Library/Caches/ms-playwright/"* "$RESOURCES_DIR/.local-browsers/" 2>/dev/null || true
    # Print message to standard output:    ✅ Playwright browsers bundled from system cache
    echo "   ✅ Playwright browsers bundled from system cache"
# Fallback branch when preceding conditions evaluate to false
else
    # Print message to standard output:    ⚠️  Playwright browsers not found — you may need to run:
    echo "   ⚠️  Playwright browsers not found — you may need to run:"
    # Print message to standard output:       .venv/bin/python3 -m playwright install chromium
    echo "      .venv/bin/python3 -m playwright install chromium"
# End of if-conditional control block
fi

# ── Step 4: Create .dmg ──
echo ""
# Print message to standard output: 💿 Creating .dmg installer...
echo "💿 Creating .dmg installer..."

# Check if create-dmg is available
if ! command -v create-dmg &> /dev/null; then
    # Print message to standard output:    ⚠️  create-dmg not found. Install with: brew install create-dmg
    echo "   ⚠️  create-dmg not found. Install with: brew install create-dmg"
    # Print message to standard output:    📁 Your .app is ready at: $DIST_DIR/$APP_NAME.app
    echo "   📁 Your .app is ready at: $DIST_DIR/$APP_NAME.app"
    # Print message to standard output:    You can manually create a DMG with Disk Utility.
    echo "   You can manually create a DMG with Disk Utility."
    # Terminate script execution with exit status 0
    exit 0
# End of if-conditional control block
fi

DMG_PATH="$DIST_DIR/${APP_NAME// /_}.dmg"

# Remove existing DMG if present
rm -f "$DMG_PATH"

# Execute command: create-dmg \
create-dmg \
    --volname "$APP_NAME" \
    --volicon "$DIST_DIR/$APP_NAME.app/Contents/Resources/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "$APP_NAME.app" 150 185 \
    --app-drop-link 450 185 \
    --hide-extension "$APP_NAME.app" \
    "$DMG_PATH" \
    "$DIST_DIR/$APP_NAME.app" \
    2>&1 || {
        # Fallback: simple DMG without fancy layout
        echo "   ⚠️  Fancy DMG failed, creating simple DMG..."
        # Execute command: hdiutil create -volname "$APP_NAME" \
        hdiutil create -volname "$APP_NAME" \
            -srcfolder "$DIST_DIR/$APP_NAME.app" \
            -ov -format UDZO \
            "$DMG_PATH"
    # Execute command: }
    }

# Print message to standard output:    ✅ DMG created at: $DMG_PATH
echo "   ✅ DMG created at: $DMG_PATH"

# ── Done ──
echo ""
# Print message to standard output: ╔═══════════════════════════════════════════════════╗
echo "╔═══════════════════════════════════════════════════╗"
# Print message to standard output: ║              🎉 Build Complete!                    ║
echo "║              🎉 Build Complete!                    ║"
# Print message to standard output: ╠═══════════════════════════════════════════════════╣
echo "╠═══════════════════════════════════════════════════╣"
# Print message to standard output: ║  .app: $DIST_DIR/$APP_NAME.app
echo "║  .app: $DIST_DIR/$APP_NAME.app"
# Print message to standard output: ║  .dmg: $DMG_PATH
echo "║  .dmg: $DMG_PATH"
# Print message to standard output: ╚═══════════════════════════════════════════════════╝
echo "╚═══════════════════════════════════════════════════╝"
