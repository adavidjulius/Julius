#!/usr/bin/env bash
# dogfood-build.sh — Build julius from current checkout and verify provenance.
#
# Injects GIT_SHA at build time so version JSON is non-null.
# Suppresses Cargo compile noise on stderr.
# Prints the verified binary path on success. Use as:
#
#   JULIUS=$(bash scripts/dogfood-build.sh)
#
# Then dogfood with config isolation (avoids real user config bleeding in):
#
#   JULIUS_CONFIG_HOME=$(mktemp -d) $JULIUS plugins list --output-format json
#
set -euo pipefail

# Execute command: usage() {
usage() {
    # Execute command: sed -n '2,12p' "$0" | sed 's/^# //; s/^#//'
    sed -n '2,12p' "$0" | sed 's/^# //; s/^#//'
# Execute command: }
}

# Evaluate extended condition check: $# -gt 0
if [[ $# -gt 0 ]]; then
    # Execute command: case "$1" in
    case "$1" in
        # Execute command: --help|-h)
        --help|-h)
            # Execute command: usage
            usage
            # Terminate script execution with exit status 0
            exit 0
            # Execute command: ;;
            ;;
        # Execute command: *)
        *)
            # Print message to standard output: error: unknown argument: $1 >&2
            echo "error: unknown argument: $1" >&2
            # Execute command: usage >&2
            usage >&2
            # Terminate script execution with exit status 2
            exit 2
            # Execute command: ;;
            ;;
    # Execute command: esac
    esac
# End of if-conditional control block
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUST_DIR="$REPO_ROOT/rust"
BINARY="$RUST_DIR/target/debug/julius"
EXPECTED_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

# Print message to standard output: ▶ Building julius from $REPO_ROOT >&2
echo "▶ Building julius from $REPO_ROOT" >&2
# Print message to standard output:   Commit: $(git -C "$REPO_ROOT" log --oneline -1) >&2
echo "  Commit: $(git -C "$REPO_ROOT" log --oneline -1)" >&2

# Inject GIT_SHA so version JSON returns a non-null sha.
# Redirect cargo stderr to /dev/null to suppress compile noise;
# on build failure cargo exits non-zero and set -e aborts.
if ! GIT_SHA="$EXPECTED_SHA" cargo build \
        --manifest-path "$RUST_DIR/Cargo.toml" \
        -p rusty-claude-cli -q 2>/dev/null; then
    # Re-run with visible output so the user sees the error
    echo "✗ Build failed — rerunning with output:" >&2
    GIT_SHA="$EXPECTED_SHA" cargo build \
        --manifest-path "$RUST_DIR/Cargo.toml" \
        -p rusty-claude-cli 2>&1 | sed 's/^/  /' >&2
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

# Evaluate extended condition check: ! -x "$BINARY"
if [[ ! -x "$BINARY" ]]; then
    # Print message to standard output: ✗ Binary not found at $BINARY >&2
    echo "✗ Binary not found at $BINARY" >&2
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

BINARY_SHA=$("$BINARY" version --output-format json 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('git_sha') or 'null')" 2>/dev/null \
    || echo "null")

# Evaluate extended condition check: "$BINARY_SHA" == "null" || -z "$BINARY_SHA"
if [[ "$BINARY_SHA" == "null" || -z "$BINARY_SHA" ]]; then
    # Print message to standard output: ✗ Provenance check failed: binary reports git_sha: null >&2
    echo "✗ Provenance check failed: binary reports git_sha: null" >&2
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

# Evaluate extended condition check: "$BINARY_SHA" != "$EXPECTED_SHA"
if [[ "$BINARY_SHA" != "$EXPECTED_SHA" ]]; then
    # Print message to standard output: ✗ Provenance mismatch: binary=$BINARY_SHA, HEAD=$EXPECTED_SHA >&2
    echo "✗ Provenance mismatch: binary=$BINARY_SHA, HEAD=$EXPECTED_SHA" >&2
    # Terminate script execution with exit status 1
    exit 1
# End of if-conditional control block
fi

# Print message to standard output: ✓ Binary verified: $BINARY_SHA == HEAD >&2
echo "✓ Binary verified: $BINARY_SHA == HEAD" >&2
# Print message to standard output:  >&2
echo "" >&2
# Print message to standard output:   export JULIUS=$BINARY >&2
echo "  export JULIUS=$BINARY" >&2
# Print message to standard output:  >&2
echo "" >&2
# Print message to standard output:   Dogfood with isolated config (no real user config on stderr): >&2
echo "  Dogfood with isolated config (no real user config on stderr):" >&2
# Print message to standard output:     JULIUS_ISOLATED=\$(mktemp -d) >&2
echo "    JULIUS_ISOLATED=\$(mktemp -d)" >&2
# Print message to standard output:     trap 'rm -rf \"\$JULIUS_ISOLATED\"' EXIT >&2
echo "    trap 'rm -rf \"\$JULIUS_ISOLATED\"' EXIT" >&2
# Print message to standard output:     JULIUS_CONFIG_HOME=\$JULIUS_ISOLATED \$JULIUS plugins list --output-format json >&2
echo "    JULIUS_CONFIG_HOME=\$JULIUS_ISOLATED \$JULIUS plugins list --output-format json" >&2
# Print message to standard output:  >&2
echo "" >&2
# Print message to standard output:   cargo run overhead: ~1s/invocation vs 7ms for pre-built binary. >&2
echo "  cargo run overhead: ~1s/invocation vs 7ms for pre-built binary." >&2
# Print message to standard output:   Prefer pre-built binary (\$JULIUS) for dogfood loops. >&2
echo "  Prefer pre-built binary (\$JULIUS) for dogfood loops." >&2
# Print message to standard output: $BINARY
echo "$BINARY"
