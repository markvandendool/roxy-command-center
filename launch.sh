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
# Use X11 backend for GTK4 compatibility on Wayland compositors
# Use venv python to ensure PyGObject access via system site-packages
export GDK_BACKEND=x11
exec "$HOME/.roxy/venv/bin/python" main.py "$@"
