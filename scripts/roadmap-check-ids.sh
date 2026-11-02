#!/usr/bin/env bash
# roadmap-check-ids.sh — fail when helper-era ROADMAP item ids are duplicated.
# Usage: scripts/roadmap-check-ids.sh [--min-id N] [path/to/ROADMAP.md]
#
# By default this validates ids >= 723, the point where ROADMAP appends started
# using scripts/roadmap-next-id.sh. Earlier ROADMAP content contains historical
# numbered lists and already-landed duplicate low ids, so the default guard is
# intentionally scoped to new helper-era append collisions. Use --min-id 1 for a
# strict whole-file audit after legacy numbering is cleaned up.
set -euo pipefail

MIN_ID=723
ROADMAP="ROADMAP.md"
ROADMAP_PATH_SEEN=0

# Repeat loop while condition evaluates to true: [[ $# -gt 0 ]]
while [[ $# -gt 0 ]]; do
  # Execute command: case "$1" in
  case "$1" in
    # Execute command: --min-id)
    --min-id)
      # Evaluate extended condition check: $# -lt 2 || ! "$2" =~ ^[0-9]+$
      if [[ $# -lt 2 || ! "$2" =~ ^[0-9]+$ ]]; then
        # Print message to standard output: error: --min-id requires a non-negative integer >&2
        echo "error: --min-id requires a non-negative integer" >&2
        # Terminate script execution with exit status 2
        exit 2
      # End of if-conditional control block
      fi
      MIN_ID="$2"
      # Execute command: shift 2
      shift 2
      # Execute command: ;;
      ;;
    # Execute command: --help|-h)
    --help|-h)
      # Execute command: sed -n '2,9p' "$0" | sed 's/^# //; s/^#//'
      sed -n '2,9p' "$0" | sed 's/^# //; s/^#//'
      # Terminate script execution with exit status 0
      exit 0
      # Execute command: ;;
      ;;
    # Execute command: --*)
    --*)
      # Print message to standard output: error: unknown option: $1 >&2
      echo "error: unknown option: $1" >&2
      # Terminate script execution with exit status 2
      exit 2
      # Execute command: ;;
      ;;
    # Execute command: *)
    *)
      # Evaluate extended condition check: "$ROADMAP_PATH_SEEN" -ne 0
      if [[ "$ROADMAP_PATH_SEEN" -ne 0 ]]; then
        # Print message to standard output: error: unexpected extra ROADMAP path: $1 >&2
        echo "error: unexpected extra ROADMAP path: $1" >&2
        # Terminate script execution with exit status 2
        exit 2
      # End of if-conditional control block
      fi
      ROADMAP="$1"
      ROADMAP_PATH_SEEN=1
      # Execute command: shift
      shift
      # Execute command: ;;
      ;;
  # Execute command: esac
  esac
# End of loop iteration block
done

# Evaluate extended condition check: ! -f "$ROADMAP"
if [[ ! -f "$ROADMAP" ]]; then
  # Print message to standard output: error: ROADMAP not found at $ROADMAP >&2
  echo "error: ROADMAP not found at $ROADMAP" >&2
  # Terminate script execution with exit status 1
  exit 1
# End of if-conditional control block
fi

# Execute command: awk -v min_id="$MIN_ID" -v path="$ROADMAP" '
awk -v min_id="$MIN_ID" -v path="$ROADMAP" '
  /^[0-9]+\./ {
    id = $0
    sub(/\..*/, "", id)
    id += 0
    if (id >= min_id) {
      count[id]++
      lines[id] = lines[id] (lines[id] ? ", " : "") FNR
    }
  }
  END {
    for (id in count) {
      if (count[id] > 1) {
        duplicate_count++
        duplicate_ids[duplicate_count] = id
      }
    }
    if (duplicate_count) {
      print "error: duplicate ROADMAP numeric id(s) in " path " (min id " min_id "):" > "/dev/stderr"
      for (i = 1; i <= duplicate_count; i++) {
        id = duplicate_ids[i]
        print "  - " id " at line(s) " lines[id] > "/dev/stderr"
      }
      exit 1
    }
    print "roadmap id check passed: no duplicate ids >= " min_id " in " path
  }
' "$ROADMAP"
