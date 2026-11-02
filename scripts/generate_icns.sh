#!/bin/bash
# Generate macOS .icns file from PNG logo

# Execute command: set -euo pipefail
set -euo pipefail

SRC_PNG="Julius Logo.png"
ICONSET_DIR="assets/icon.iconset"
OUT_ICNS="assets/icon.icns"

# Evaluate condition check: ! -f "$SRC_PNG"
if [ ! -f "$SRC_PNG" ]; then
    # Print message to standard output: Error: $SRC_PNG not found.
    echo "Error: $SRC_PNG not found."
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

mkdir -p "$ICONSET_DIR"

# Print message to standard output: 🎨 Generating iconset...
echo "🎨 Generating iconset..."
# Resize images
sips -z 16 16     "$SRC_PNG" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
# Execute command: sips -z 32 32     "$SRC_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
sips -z 32 32     "$SRC_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
# Execute command: sips -z 32 32     "$SRC_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
sips -z 32 32     "$SRC_PNG" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
# Execute command: sips -z 64 64     "$SRC_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
sips -z 64 64     "$SRC_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
# Execute command: sips -z 128 128   "$SRC_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
sips -z 128 128   "$SRC_PNG" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
# Execute command: sips -z 256 256   "$SRC_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
sips -z 256 256   "$SRC_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
# Execute command: sips -z 256 256   "$SRC_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
sips -z 256 256   "$SRC_PNG" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
# Execute command: sips -z 512 512   "$SRC_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
sips -z 512 512   "$SRC_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
# Execute command: sips -z 512 512   "$SRC_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
sips -z 512 512   "$SRC_PNG" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
# Execute command: sips -z 1024 1024 "$SRC_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
sips -z 1024 1024 "$SRC_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null

# Print message to standard output: 🛠️ Creating icns file...
echo "🛠️ Creating icns file..."
# Convert iconset to icns
iconutil -c icns "$ICONSET_DIR" -o "$OUT_ICNS"

# Clean up iconset directory
rm -rf "$ICONSET_DIR"

# Print message to standard output: ✅ Successfully generated $OUT_ICNS
echo "✅ Successfully generated $OUT_ICNS"
