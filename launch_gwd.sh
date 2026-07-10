#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./launch.sh "$@" &
LAUNCHER_PID=$!

for _ in $(seq 1 20); do
    HEALTH="$(python3 tools/runtime_check.py native-health --no-backends 2>/dev/null || true)"
    WINDOW_ID="$(printf '%s' "$HEALTH" | python3 -c 'import json,sys; data=json.load(sys.stdin); windows=data.get("windows", []); print(windows[0]["windowId"] if len(windows) == 1 else "")' 2>/dev/null || true)"
    if [[ -n "$WINDOW_ID" ]]; then
        xdotool windowmove "$WINDOW_ID" 4787 0
        xdotool windowsize "$WINDOW_ID" 1920 1080
        break
    fi
    sleep 0.3
done

wait "$LAUNCHER_PID"
