#!/usr/bin/env python3
"""
Voice PTT Trigger — Called from control-surfaces kernel (device ingress bridge).

Runs a full push-to-talk cycle via VoiceCommandService:
  1. Start dictation recording
  2. Record for N seconds (default 5.0)
  3. Stop, transcribe, route intent, speak response
  4. Write receipts

Usage:
  python3 scripts/voice-ptt-trigger.py [--duration 5.0]

Exit codes:
  0 = success (transcript captured and routed)
  1 = start failed
  2 = empty transcript
  3 = execution error
"""

import sys
import argparse
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from services.voice_command_service import get_voice_command_service


def main():
    parser = argparse.ArgumentParser(description="Roxy voice PTT trigger")
    parser.add_argument("--duration", type=float, default=5.0, help="Recording duration in seconds")
    args = parser.parse_args()

    svc = get_voice_command_service()

    print(f"[voice-ptt] Starting recording (duration={args.duration}s)...", flush=True)
    start = svc.start_recording()
    if not start.get("ok"):
        print(f"[voice-ptt] START FAILED: {start.get('error', 'unknown')}", flush=True)
        sys.exit(1)

    import time
    time.sleep(args.duration)

    print("[voice-ptt] Stopping and routing...", flush=True)
    result = svc.stop_recording()

    if not result.get("ok"):
        print(f"[voice-ptt] STOP FAILED: {result.get('error', 'unknown')}", flush=True)
        sys.exit(1)

    if not result.get("routed"):
        reason = result.get("reason", "no speech")
        print(f"[voice-ptt] NO COMMAND: {reason}", flush=True)
        sys.exit(2)

    transcript = result.get("transcript", "")
    action = result.get("action", "unknown")
    response = result.get("response", "")
    receipt = result.get("receiptPath", "")

    print(f"[voice-ptt] TRANSCRIPT: '{transcript}'", flush=True)
    print(f"[voice-ptt] ACTION: {action}", flush=True)
    print(f"[voice-ptt] RESPONSE: {response}", flush=True)
    print(f"[voice-ptt] RECEIPT: {receipt}", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
