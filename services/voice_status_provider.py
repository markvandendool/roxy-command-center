#!/usr/bin/env python3
"""
Voice Foundry Status Provider — Read-only readiness classification.

Checks Piper, Whisper, OpenWakeWord, TTS, STT routes.
Classifies: READY | DORMANT | MISSING_SERVICE | PATH_ISSUE | BLOCKED
"""

import socket
from pathlib import Path
from typing import Dict, Any

# Known service ports
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
        import urllib.request
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"ok": True, "status": resp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_voice_status() -> Dict[str, Any]:
    """Classify Voice Foundry readiness."""
    piper = _probe_tcp(PIPER_PORT)
    whisper = _probe_tcp(WHISPER_PORT)
    openwakeword = _probe_tcp(OPENWAKEWORD_PORT)

    # Check for existing TTS/STT scripts or configs
    tts_config = Path("/home/mark/.config/piper")  # common Piper config path
    stt_config = Path("/home/mark/.config/whisper")  # common Whisper config path

    services = {
        "piper": {"port": PIPER_PORT, "alive": piper, "config": tts_config.exists()},
        "whisper": {"port": WHISPER_PORT, "alive": whisper, "config": stt_config.exists()},
        "openwakeword": {"port": OPENWAKEWORD_PORT, "alive": openwakeword, "config": False},
    }

    alive_count = sum(1 for s in services.values() if s["alive"])
    config_count = sum(1 for s in services.values() if s["config"])

    # Classification
    if alive_count >= 2:
        classification = "READY"
        blocker = None
    elif alive_count == 1:
        classification = "DORMANT"
        blocker = "Only one voice service alive"
    elif config_count > 0:
        classification = "MISSING_SERVICE"
        blocker = "Config exists but services not running"
    else:
        classification = "BLOCKED"
        blocker = "No voice services configured or running"

    return {
        "schemaVersion": "voice-foundry-status.v1",
        "classification": classification,
        "services": services,
        "aliveCount": alive_count,
        "configCount": config_count,
        "blocker": blocker,
        "recommendation": _recommendation(classification),
    }


def _recommendation(cls: str) -> str:
    return {
        "READY": "Voice Foundry is operational.",
        "DORMANT": "Start remaining voice services to activate Voice Foundry.",
        "MISSING_SERVICE": "Services have config but are not running. Start them.",
        "BLOCKED": "No voice pipeline configured. Install Piper + Whisper + OpenWakeWord.",
    }.get(cls, "Unknown status.")
