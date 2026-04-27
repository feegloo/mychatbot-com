#!/usr/bin/env bash
# Local runner for the Ralph Wiggum loop.
# Usage:
#   ./run.sh --task my-feature --iterations 10
#   ./run.sh --task my-feature --hitl              # single iteration, no commit
#   ./run.sh --task my-feature --sandbox           # run inside docker sandbox
set -euo pipefail

cd "$(dirname "$0")"

SANDBOX=0
PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --sandbox) SANDBOX=1 ;;
    *) PASSTHROUGH+=("$arg") ;;
  esac
done

if [[ "$SANDBOX" -eq 1 ]]; then
  python3.11 - <<PY "$@"
import sys
from pathlib import Path
from sandbox import run_in_sandbox, is_available
if not is_available():
    print("docker not available; cannot use --sandbox", file=sys.stderr); sys.exit(2)
repo = Path(__file__).resolve().parent.parent
argv = ["python3.11", "ralph/agent_ralph_loop.py"] + [a for a in sys.argv[1:] if a != "--sandbox"]
sys.exit(run_in_sandbox(repo, argv))
PY
  exit $?
fi

exec python3.11 agent_ralph_loop.py "${PASSTHROUGH[@]}"
