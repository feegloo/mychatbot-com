#!/usr/bin/env bash
# Disable nightly shutdown: removes chatrag-sleep and chatrag-wake scheduler jobs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/worker-manage.sh" remove-main-schedule
