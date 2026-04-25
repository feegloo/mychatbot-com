#!/usr/bin/env bash
# publish-appstore.sh — Build and upload a ChatRAG iOS build to App Store Connect.
#
# Required env vars:
#   APPLE_ID                   — Your Apple ID email (e.g. you@example.com)
#   APPLE_APP_SPECIFIC_PASSWORD — App-specific password from appleid.apple.com
#   APPLE_TEAM_ID               — 10-char Team ID from developer.apple.com/account
#
# Optional env vars:
#   SKIP_BUILD=1               — Skip `tauri ios build` (use an already-built IPA)
#   IPA_PATH                   — Explicit path to .ipa file (auto-detected when unset)
#
# Upload methods supported (in order of preference):
#   1. xcrun altool --upload-app  (works with Xcode 14+, deprecated but reliable)
#   2. xcrun transporter -m upload  (newer Transporter CLI, requires Transporter.app)
#
# Docs: https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/
#       https://developer.apple.com/documentation/technotes/tn3147-migrating-to-the-latest-notarization-tool

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAURI_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_TAURI="$TAURI_DIR/src-tauri"
GEN_APPLE="$SRC_TAURI/gen/apple"

# ── prerequisite checks ────────────────────────────────────────────────────────

check_env() {
  local missing=()
  [[ -z "${APPLE_ID:-}" ]]                    && missing+=("APPLE_ID")
  [[ -z "${APPLE_APP_SPECIFIC_PASSWORD:-}" ]]  && missing+=("APPLE_APP_SPECIFIC_PASSWORD")
  [[ -z "${APPLE_TEAM_ID:-}" ]]               && missing+=("APPLE_TEAM_ID")

  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "❌  Missing required environment variables:"
    for v in "${missing[@]}"; do
      echo "    export $v=<value>"
    done
    echo ""
    echo "Tip: Create an app-specific password at https://appleid.apple.com"
    echo "     and find your Team ID at https://developer.apple.com/account"
    exit 1
  fi
}

check_xcode() {
  if ! xcode-select -p &>/dev/null || [[ "$(xcode-select -p)" == *"CommandLineTools"* ]]; then
    echo "❌  Full Xcode.app is required (Command Line Tools alone are not enough)."
    echo "    Install Xcode from https://apps.apple.com/app/xcode/id497799835"
    echo "    Then run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
    exit 1
  fi
}

check_altool_or_transporter() {
  if xcrun --find altool &>/dev/null; then
    UPLOAD_METHOD="altool"
  elif xcrun --find transporter &>/dev/null; then
    UPLOAD_METHOD="transporter"
  else
    echo "❌  Neither altool nor Transporter CLI found."
    echo "    Install Transporter from the Mac App Store:"
    echo "    https://apps.apple.com/app/transporter/id1450874784"
    exit 1
  fi
}

# ── build ──────────────────────────────────────────────────────────────────────

run_build() {
  if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
    echo "⏭   Skipping build (SKIP_BUILD=1)."
    return
  fi

  echo "🔨  Building iOS release…"
  cd "$TAURI_DIR"
  # Source Cargo env in case rustup isn't on PATH yet
  [[ -f "$HOME/.cargo/env" ]] && source "$HOME/.cargo/env"
  npx tauri ios build --release
}

# ── locate IPA ─────────────────────────────────────────────────────────────────

find_ipa() {
  if [[ -n "${IPA_PATH:-}" ]]; then
    if [[ ! -f "$IPA_PATH" ]]; then
      echo "❌  IPA_PATH set but file not found: $IPA_PATH"
      exit 1
    fi
    echo "$IPA_PATH"
    return
  fi

  # Tauri 2 ios build places the IPA under gen/apple/build/
  # Common patterns:  build/arm64/<ProductName>.ipa
  #                   build/release/<ProductName>.ipa
  local ipa
  ipa=$(find "$GEN_APPLE/build" -name "*.ipa" 2>/dev/null | head -1)

  if [[ -z "$ipa" ]]; then
    echo "❌  No .ipa file found under $GEN_APPLE/build/"
    echo "    Run the build manually first, or set IPA_PATH=/path/to/App.ipa"
    exit 1
  fi

  echo "$ipa"
}

# ── upload ─────────────────────────────────────────────────────────────────────

upload_ipa() {
  local ipa="$1"
  echo "📦  IPA: $ipa"
  echo "⬆️   Uploading to App Store Connect via $UPLOAD_METHOD…"

  case "$UPLOAD_METHOD" in
    altool)
      # --output-format xml gives structured output; remove for human-readable
      xcrun altool \
        --upload-app \
        --type ios \
        --file "$ipa" \
        --username "$APPLE_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --asc-provider "$APPLE_TEAM_ID"
      ;;
    transporter)
      xcrun transporter \
        -m upload \
        -u "$APPLE_ID" \
        -p "$APPLE_APP_SPECIFIC_PASSWORD" \
        -f "$ipa"
      ;;
  esac
}

# ── main ───────────────────────────────────────────────────────────────────────

main() {
  echo "🚀  ChatRAG — App Store publish"
  echo ""

  check_env
  check_xcode
  check_altool_or_transporter

  run_build

  local ipa
  ipa=$(find_ipa)

  upload_ipa "$ipa"

  echo ""
  echo "✅  Upload complete!"
  echo "    The build will be processed by Apple (usually 5–30 min)."
  echo "    You'll receive an email when it's ready in App Store Connect."
  echo "    Next: go to https://appstoreconnect.apple.com → your app → TestFlight or submit for review."
}

main "$@"
