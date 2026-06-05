#!/bin/bash
# ROXY Command Center Launch + PID Tracking
# Usage: ./launch_cc.sh [stop|restart|status]

set -e

PIDFILE="$HOME/.cache/roxy-command-center/cc.pid"
LOGFILE="$HOME/.cache/roxy-command-center/run.log"
APP_DIR="$HOME/.roxy/apps/roxy-command-center"

mkdir -p "$(dirname "$PIDFILE")"

case "${1:-start}" in
    stop)
        if [ -f "$PIDFILE" ]; then
            PID=$(cat "$PIDFILE")
            echo "Stopping Command Center (PID $PID)..."
            # Try SIGTERM first
            if kill -TERM "$PID" 2>/dev/null; then
                echo "Sent SIGTERM to $PID, waiting up to 10 seconds..."
                for i in {1..10}; do
                    if ! kill -0 "$PID" 2>/dev/null; then
                        echo "Process $PID exited gracefully"
                        rm -f "$PIDFILE"
                        exit 0
                    fi
                    sleep 1
                done
                # Still alive, force kill
                echo "Process $PID did not exit, sending SIGKILL..."
                kill -KILL "$PID" 2>/dev/null || true
                sleep 1
            fi
            rm -f "$PIDFILE"
            echo "Stopped"
        else
            echo "No PID file found"
        fi
        ;;
    
    status)
        if [ -f "$PIDFILE" ]; then
            PID=$(cat "$PIDFILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Command Center running (PID $PID)"
                ps -p "$PID" -o pid,ppid,cmd,etime
            else
                echo "PID file exists but process $PID is not running"
                rm -f "$PIDFILE"
            fi
        else
            echo "Command Center not running"
        fi
        ;;
    
    restart)
        "$0" stop
        sleep 2
        "$0" start
        ;;
    
    start)
        # Check if already running
        if [ -f "$PIDFILE" ]; then
            OLD_PID=$(cat "$PIDFILE")
            if kill -0 "$OLD_PID" 2>/dev/null; then
                echo "Command Center already running (PID $OLD_PID)"
                exit 1
            else
                echo "Removing stale PID file"
                rm -f "$PIDFILE"
            fi
        fi
        
        echo "Starting ROXY Command Center..."
        cd "$APP_DIR"

        # Start in background, redirect output
        # Use X11 backend for GTK4 compatibility on Wayland compositors
        # Use venv python to ensure PyGObject access via system site-packages
        DISPLAY=:0 GDK_BACKEND=x11 "$HOME/.roxy/venv/bin/python" main.py > "$LOGFILE" 2>&1 &
        PID=$!
        
        # Store PID
        echo "$PID" > "$PIDFILE"
        
        # Wait a moment to see if it crashes immediately
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "Command Center started successfully (PID $PID)"
            echo "Logs: $LOGFILE"
            echo "PID: $PIDFILE"
        else
            echo "Command Center failed to start"
            rm -f "$PIDFILE"
            echo "Last 20 lines of log:"
            tail -20 "$LOGFILE"
            exit 1
        fi
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
