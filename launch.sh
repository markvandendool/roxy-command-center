#!/bin/bash
# ROXY Command Center Launcher
# Ensures single instance and proper environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Kill existing instance if running
pkill -f "python3 main.py" 2>/dev/null

# Small delay for cleanup
sleep 0.3

# Launch with proper environment
exec python3 main.py "$@"
