#!/usr/bin/env python3
"""
Voice Foundry Status Provider — Read-only readiness classification.

Checks the actual voice stack that exists on this machine:
- Dictation daemon :10500 (STT via faster-whisper)
- Voice Foundry :8788 (TTS via F5-TTS / kokoro)
- Legacy Piper/Whisper/OpenWakeWord ports for backward compatibility

Classifies: READY | PARTIAL | DORMANT | MISSING_SERVICE | PATH_ISSUE | BLOCKED
"""

import json
import socket
import urllib.request
from pathlib import Path
from typing import Dict, Any

# Actual service ports on this machine
DICTATION_PORT = 10500
VOICE_FOUNDRY_PORT = 8788

# Legacy service ports (kept for backward compatibility probes)
PIPER_PORT = 10200
WHISPER_PORT = 10300
OPENWAKEWORD_PORT = 10400


def _probe_tcp(port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


def _probe_http(url: str, timeout: float = 2.0) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            try:
                body = json.loads(data)
            except Exception:
                body = {"raw": data[:200]}
            return {"ok": True, "status": resp.status, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _probe_dictation() -> Dict[str, Any]:
    """Probe the dictation daemon on :10500."""
    if not _probe_tcp(DICTATION_PORT):
        return {"alive": False, "error": "port closed"}
    return _probe_http(f"http://127.0.0.1:{DICTATION_PORT}/health")


def _probe_voice_foundry() -> Dict[str, Any]:
    """Probe the Voice Foundry TTS service on :8788."""
    if not _probe_tcp(VOICE_FOUNDRY_PORT):
        return {"alive": False, "error": "port closed"}
    return _probe_http(f"http://127.0.0.1:{VOICE_FOUNDRY_PORT}/voice/health")


def get_voice_status() -> Dict[str, Any]:
    """Classify Voice Foundry readiness based on actual services."""
    dictation = _probe_dictation()
    voice_foundry = _probe_voice_foundry()

    # Legacy probes
    piper = _probe_tcp(PIPER_PORT)
    whisper = _probe_tcp(WHISPER_PORT)
    openwakeword = _probe_tcp(OPENWAKEWORD_PORT)

    services = {
        "dictation": {
            "port": DICTATION_PORT,
            "alive": dictation.get("ok", False),
            "role": "STT (faster-whisper)",
            "detail": dictation.get("body") if dictation.get("ok") else dictation.get("error"),
        },
        "voiceFoundry": {
            "port": VOICE_FOUNDRY_PORT,
            "alive": voice_foundry.get("ok", False),
            "role": "TTS (F5-TTS / kokoro / ElevenLabs proxy)",
            "detail": voice_foundry.get("body") if voice_foundry.get("ok") else voice_foundry.get("error"),
        },
        "piper": {"port": PIPER_PORT, "alive": piper, "role": "legacy TTS"},
        "whisper": {"port": WHISPER_PORT, "alive": whisper, "role": "legacy STT"},
        "openWakeWord": {"port": OPENWAKEWORD_PORT, "alive": openwakeword, "role": "legacy wake word"},
    }

    stt_alive = services["dictation"]["alive"]
    tts_alive = services["voiceFoundry"]["alive"]

    if stt_alive and tts_alive:
        classification = "READY"
        blocker = None
    elif stt_alive and not tts_alive:
        classification = "PARTIAL"
        blocker = "STT dictation is ready on :10500, but TTS Voice Foundry (:8788) is not running. Voice commands can be understood; responses are text-only until TTS starts."
    elif tts_alive and not stt_alive:
        classification = "PARTIAL"
        blocker = "TTS Voice Foundry is ready on :8788, but STT dictation (:10500) is not running."
    else:
        classification = "BLOCKED"
        blocker = "No voice services are running. Start dictation daemon on :10500 and Voice Foundry on :8788."

    return {
        "schemaVersion": "voice-foundry-status.v2",
        "classification": classification,
        "services": services,
        "sttAlive": stt_alive,
        "ttsAlive": tts_alive,
        "blocker": blocker,
        "recommendation": _recommendation(classification),
        "note": "Legacy ports 10200/10300/10400 are not used by the actual MindSong voice stack.",
    }


def _recommendation(cls: str) -> str:
    return {
        "READY": "Voice pipeline is operational: STT + TTS both up.",
        "PARTIAL": "Voice pipeline is partially operational. Push-to-talk works; spoken responses require TTS.",
        "DORMANT": "Some voice services are present but not all are running.",
        "MISSING_SERVICE": "Services have config but are not running. Start them.",
        "BLOCKED": "No voice pipeline running. Start dictation daemon (:10500) and Voice Foundry (:8788).",
    }.get(cls, "Unknown status.")
