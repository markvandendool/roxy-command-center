#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

case "${1:-start}" in
    start)
        exec ./launch.sh
        ;;
    status)
        exec python3 tools/runtime_check.py native-health
        ;;
    stop|restart)
        printf 'RCC_EXACT_WINDOW_CLOSE_REQUIRED action=%s\n' "$1" >&2
        printf 'Close the verified native window normally; blind PID-file termination is retired.\n' >&2
        exit 2
        ;;
    *)
        printf 'Usage: %s {start|status}\n' "$0" >&2
        exit 2
        ;;
esac
