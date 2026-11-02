#!/usr/bin/env bash
# Convert a DXF to DWG using the free ODA File Converter.
#
# One-time setup (install the converter):
#   1. Download from https://www.opendesign.com/guestfiles/oda_file_converter
#   2. Install to /Applications/ODAFileConverter.app
#
# Usage:
#   ./dxf_to_dwg.sh <input.dxf> [output.dwg]
set -euo pipefail

# Evaluate extended condition check: $# -lt 1
if [[ $# -lt 1 ]]; then
  # Print message to standard output: usage: $0 <input.dxf> [output.dwg] >&2
  echo "usage: $0 <input.dxf> [output.dwg]" >&2
  # Terminate script execution with exit status 2
  exit 2
# End of if-conditional control block
fi

INPUT="$1"
OUTPUT="${2:-${INPUT%.dxf}.dwg}"

# Evaluate extended condition check: ! -f "$INPUT"
if [[ ! -f "$INPUT" ]]; then
  # Print message to standard output: input not found: $INPUT >&2
  echo "input not found: $INPUT" >&2
  # Terminate script execution with exit status 1
  exit 1
# End of if-conditional control block
fi

# 1. Try LibreDWG dxf2dwg (fast, CLI, native)
if command -v dxf2dwg >/dev/null 2>&1; then
  # Execute command: dxf2dwg -y "$INPUT" -o "$OUTPUT"
  dxf2dwg -y "$INPUT" -o "$OUTPUT"
  # Print message to standard output: ✅ Converted to DWG via dxf2dwg: $OUTPUT
  echo "✅ Converted to DWG via dxf2dwg: $OUTPUT"
  # Terminate script execution with exit status 0
  exit 0
# Alternative extended condition check: -x "/opt/homebrew/bin/dxf2dwg"
elif [[ -x "/opt/homebrew/bin/dxf2dwg" ]]; then
  # Execute command: /opt/homebrew/bin/dxf2dwg -y "$INPUT" -o "$OUTPUT"
  /opt/homebrew/bin/dxf2dwg -y "$INPUT" -o "$OUTPUT"
  # Print message to standard output: ✅ Converted to DWG via dxf2dwg: $OUTPUT
  echo "✅ Converted to DWG via dxf2dwg: $OUTPUT"
  # Terminate script execution with exit status 0
  exit 0
# End of if-conditional control block
fi

# 2. Fall back to ODA File Converter
CONVERTER=""
# Execute command: for c in \
for c in \
  "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter" \
  "$HOME/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter" \
  "$(command -v ODAFileConverter 2>/dev/null || true)"; do
  # Evaluate extended condition check: -n "$c" && -x "$c"
  if [[ -n "$c" && -x "$c" ]]; then
    CONVERTER="$c"
    # Execute command: break
    break
  # End of if-conditional control block
  fi
# End of loop iteration block
done

# Evaluate extended condition check: -z "$CONVERTER"
if [[ -z "$CONVERTER" ]]; then
  # Execute command: cat >&2 <<'EOF'
  cat >&2 <<'EOF'
ODA File Converter is not installed.

Install it once (free): https://www.opendesign.com/guestfiles/oda_file_converter
Then re-run this script.

Alternative without installing anything: open the DXF in AutoCAD and choose
File > Save As > AutoCAD Drawing (*.dwg).
EOF
  # Terminate script execution with exit status 1
  exit 1
# End of if-conditional control block
fi

IN_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
OUT_DIR="$(cd "$(dirname "$OUTPUT")" && pwd)"
BASE="$(basename "$INPUT")"

# ODA signature: <in_dir> <out_dir> <in_ver> <out_ver> <recurse> <audit> <filter>
"$CONVERTER" "$IN_DIR" "$OUT_DIR" "ACAD2010" "ACAD2018" "0" "1" "$BASE"

# Print message to standard output: done. check $OUT_DIR
echo "done. check $OUT_DIR"
