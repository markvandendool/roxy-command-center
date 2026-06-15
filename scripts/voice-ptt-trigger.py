#!/usr/bin/env python3
"""
Voice PTT Trigger — Enhanced with RCC brain + Jessica TTS pipeline.

Called from control-surfaces kernel (device ingress bridge).
If SSOT pipeline is available, uses it for natural language queries.
Falls back to legacy hardcoded intents if SSOT is unavailable.

Usage:
  python3 scripts/voice-ptt-trigger.py [--duration 5.0] [--legacy]
"""

import sys
import time
import json
import urllib.request
from pathlib import Path
from typing import Optional

# Try to use the enhanced SSOT pipeline
SSOT_VOICE_DIR = Path("/mnt/work/ssot/mindsong-juke-hub/scripts/voice/roxy-wake")
USE_LEGACY = False


def try_enhanced_pipeline(duration_s: float) -> bool:
    """Try the enhanced RCC+Jessica pipeline. Returns True if succeeded."""
    try:
        sys.path.insert(0, str(SSOT_VOICE_DIR))
        from brain import answer_query
        from tts_jessica import speak

        DICTATION_URL = "http://127.0.0.1:10500"

        def dictate_toggle():
            req = urllib.request.Request(
                f"{DICTATION_URL}/dictate/toggle",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        # Start
        start = dictate_toggle()
        if not start.get("ok"):
            print(f"[voice-ptt] START FAILED: {start.get('error')}", flush=True)
            return False

        print(f"[voice-ptt] Recording {duration_s}s...", flush=True)
        time.sleep(duration_s)

        # Stop
        stop = dictate_toggle()
        if not stop.get("ok"):
            print(f"[voice-ptt] STOP FAILED: {stop.get('error')}", flush=True)
            return False

        transcript = stop.get("transcript", "").strip()
        if not transcript:
            print("[voice-ptt] No speech captured", flush=True)
            return True  # Not a failure, just no speech

        print(f"[voice-ptt] Transcript: '{transcript}'", flush=True)

        # Brain
        print("[voice-ptt] Thinking...", flush=True)
        response = answer_query(transcript)
        print(f"[voice-ptt] Response: {response}", flush=True)

        # TTS
        result = speak(response, play=True)
        print(json.dumps(result, indent=2))
        return True

    except Exception as e:
        print(f"[voice-ptt] Enhanced pipeline failed: {e}", flush=True)
        return False


def legacy_pipeline(duration_s: float) -> bool:
    """Fallback to legacy hardcoded intents."""
    REPO_ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(REPO_ROOT))
    from services.voice_command_service import get_voice_command_service

    svc = get_voice_command_service()

    print(f"[voice-ptt] Legacy mode (duration={duration_s}s)...", flush=True)
    start = svc.start_recording()
    if not start.get("ok"):
        print(f"[voice-ptt] START FAILED", flush=True)
        return False

    time.sleep(duration_s)

    result = svc.stop_recording()
    if not result.get("ok"):
        print(f"[voice-ptt] STOP FAILED", flush=True)
        return False

    if not result.get("routed"):
        print(f"[voice-ptt] No command routed", flush=True)
        return True

    print(f"[voice-ptt] Action: {result.get('action')}")
    print(f"[voice-ptt] Response: {result.get('response')}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Roxy voice PTT trigger")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--legacy", action="store_true", help="Use legacy hardcoded intents")
    args = parser.parse_args()

    if args.legacy:
        ok = legacy_pipeline(args.duration)
    else:
        ok = try_enhanced_pipeline(args.duration)
        if not ok:
            print("[voice-ptt] Falling back to legacy pipeline...", flush=True)
            ok = legacy_pipeline(args.duration)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
