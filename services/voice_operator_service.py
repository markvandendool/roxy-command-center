#!/usr/bin/env python3
"""
Voice Operator Service — RCC-backed conversational Roxy for GTK4.

Delegates to SSOT roxy_voice_operator.py via RCC commands.
No voice logic lives here. Pure RCC client.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

SSOT_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")
ROXY_VOICE_OP = SSOT_ROOT / "scripts" / "voice" / "roxy-wake" / "roxy_voice_operator.py"
PYTHON = "/home/mark/.venvs/roxy-wake/bin/python"

# Voice aliases mapped to Voice Foundry presets
VOICE_ALIASES = {
    "mark_owner": "mark_owner",
    "rocky_tutor": "rocky_tutor",
    "roxy_jessica": "roxy_jessica",
    "kimi_agent": "kimi_agent",
    "codex_agent": "codex_agent",
    "regent_agent": "regent_agent",
    "agent_default": "agent_default",
}


class VoiceOperatorService:
    """RCC-backed voice operator. GTK4 is a thin shell."""

    def __init__(self):
        self._last_transcript: Optional[str] = None
        self._last_response: Optional[str] = None
        self._last_audio_path: Optional[str] = None
        self._last_receipt: Optional[str] = None

    def ask(self, text: str, voice: str = "mark_owner", provider: str = "voice_foundry") -> Dict[str, Any]:
        """Text → brain → TTS via roxy_voice_operator.py."""
        preset = VOICE_ALIASES.get(voice, voice)
        cmd = [
            PYTHON, str(ROXY_VOICE_OP),
            "--text", text,
            "--voice", preset,
            "--provider", provider,
            "--json",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(SSOT_ROOT),
            )
            lines = result.stdout.strip().split("\n")
            json_line = next((l for l in reversed(lines) if l.strip().startswith("{")), "{}")
            data = json.loads(json_line)
            self._last_transcript = data.get("transcript", text)
            self._last_response = data.get("response", "")
            self._last_audio_path = data.get("audioPath")
            self._last_receipt = data.get("receiptPath")
            return {"ok": data.get("ok", False), **data}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def speak(self, text: str, voice: str = "mark_owner") -> Dict[str, Any]:
        """Speak text directly via Voice Foundry."""
        preset = VOICE_ALIASES.get(voice, voice)
        vf_client = SSOT_ROOT / "scripts" / "voice" / "roxy-wake" / "voice_foundry_client.py"
        cmd = [PYTHON, str(vf_client), text, "--voice", preset, "--play"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(SSOT_ROOT))
            return {"ok": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_last_interaction(self) -> Dict[str, Any]:
        """Return last transcript/response/audio for UI display."""
        return {
            "transcript": self._last_transcript,
            "response": self._last_response,
            "audioPath": self._last_audio_path,
            "receiptPath": self._last_receipt,
        }


# Singleton
_voice_op_svc: Optional[VoiceOperatorService] = None


def get_voice_operator_service() -> VoiceOperatorService:
    global _voice_op_svc
    if _voice_op_svc is None:
        _voice_op_svc = VoiceOperatorService()
    return _voice_op_svc
