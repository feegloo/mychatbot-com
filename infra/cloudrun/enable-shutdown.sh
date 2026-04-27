#!/usr/bin/env bash
# Enable nightly shutdown: chatrag main service sleeps at 01:00 UTC, wakes at 09:00 UTC.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/worker-manage.sh" 2>/dev/null || true
exec "${SCRIPT_DIR}/worker-manage.sh" setup-main-schedule 1 9
