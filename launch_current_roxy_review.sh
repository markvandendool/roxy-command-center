#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== ROXY Command Center current-runtime review launch ==="
echo "This is foreground-only. No services are installed or started."
echo

./tools/runtime_check.py
echo
echo "Runtime check passed. Starting GTK app in foreground..."
exec python3 main.py
