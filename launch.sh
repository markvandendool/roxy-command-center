#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
RUNTIME_DIR="$HOME/.cache/roxy-command-center"
LOG_FILE="$RUNTIME_DIR/run.log"

cd "$SCRIPT_DIR"
mkdir -p "$RUNTIME_DIR"

export DISPLAY="${DISPLAY:-:1}"
export XAUTHORITY="${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}"
export GDK_BACKEND="${GDK_BACKEND:-x11}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export RCC_SOURCE_COMMIT="${RCC_SOURCE_COMMIT:-$(git rev-parse HEAD)}"

set +e
PREPARE_OUTPUT="$(python3 tools/runtime_check.py prepare-launch 2>&1)"
PREPARE_STATUS=$?
set -e
printf '%s\n' "$PREPARE_OUTPUT" | tee -a "$LOG_FILE"

case "$PREPARE_STATUS" in
    0)
        ;;
    10)
        exit 0
        ;;
    *)
        printf 'RCC_LAUNCH_REFUSED status=%s\n' "$PREPARE_STATUS" | tee -a "$LOG_FILE" >&2
        exit "$PREPARE_STATUS"
        ;;
esac

exec python3 -X faulthandler -u main.py "$@" >>"$LOG_FILE" 2>&1
