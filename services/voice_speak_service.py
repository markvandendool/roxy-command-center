#!/usr/bin/env python3
"""
Voice Speak Service — Professional TTS for Roxy Command Center.

Routes:
1. ElevenLabs API (Jessica voice) — primary, world-class quality
2. espeak-ng — fallback, local, immediate

Reads ElevenLabs API key from SSOT .env.local (never prints it).
Writes speak receipts to output/roxy-command-center/voice-speaks/.
"""

import json
import os
import subprocess
import tempfile
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from services.action_receipt_service import write_action_receipt

# ── Configuration ────────────────────────────────────────────────────────────

ELEVENLABS_VOICE_ID = "cgSgspJ2msm6clMCkdW9"  # Jessica
ELEVENLABS_MODEL = "eleven_multilingual_v2"
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Try to read API key from SSOT .env.local
_SSOT_ENV_PATH = Path("/mnt/work/ssot/mindsong-juke-hub/.env.local")


def _load_api_key() -> Optional[str]:
    """Read ElevenLabs API key from SSOT .env.local. Never print it."""
    if not _SSOT_ENV_PATH.exists():
        return None
    try:
        for line in _SSOT_ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("VITE_ELEVENLABS_API_KEY=") or line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


# Lazy-loaded key
_API_KEY: Optional[str] = None


def _get_api_key() -> Optional[str]:
    global _API_KEY
    if _API_KEY is None:
        _API_KEY = _load_api_key()
    return _API_KEY


def _ts() -> str:
    return datetime.now().isoformat()


class VoiceSpeakService:
    """Server-side TTS for Roxy. ElevenLabs primary, espeak-ng fallback."""

    def __init__(self):
        self._api_key = _get_api_key()
        self._last_audio_path: Optional[str] = None
        self._last_provider: Optional[str] = None

    def is_available(self) -> bool:
        """Check if any speak path is available."""
        if self._api_key:
            return True
        if self._espeak_available():
            return True
        return False

    def _espeak_available(self) -> bool:
        try:
            subprocess.run(["espeak-ng", "--version"], capture_output=True, check=True)
            return True
        except Exception:
            return False

    def speak(
        self,
        text: str,
        voice_id: Optional[str] = None,
        use_case: str = "operator-response",
        source: str = "voice-command",
    ) -> Dict[str, Any]:
        """Speak text aloud. Try ElevenLabs first, fall back to espeak-ng."""
        receipt_payload = {
            "text": text,
            "requestedVoice": voice_id or ELEVENLABS_VOICE_ID,
            "useCase": use_case,
            "source": source,
        }

        # Try ElevenLabs if key is available
        if self._api_key:
            try:
                result = self._speak_elevenlabs(text, voice_id or ELEVENLABS_VOICE_ID)
                receipt = write_action_receipt(
                    action="voice_speak",
                    mission_id="voice-speak",
                    mission_title=f"Speak: {text[:60]}",
                    status="completed",
                    target_agent="elevenlabs",
                    target_lane="voice-tts",
                    authority="operator",
                    payload={**receipt_payload, "provider": "elevenlabs", **result},
                    next_action="playback complete",
                )
                return {**result, "receiptPath": str(receipt)}
            except Exception as e:
                # ElevenLabs failed — fall through to espeak
                receipt_payload["elevenlabs_error"] = str(e)

        # Fallback: espeak-ng
        try:
            result = self._speak_espeak(text)
            receipt = write_action_receipt(
                action="voice_speak",
                mission_id="voice-speak",
                mission_title=f"Speak: {text[:60]}",
                status="completed",
                target_agent="espeak-ng",
                target_lane="voice-tts",
                authority="operator",
                payload={**receipt_payload, "provider": "espeak-ng", **result},
                next_action="playback complete",
            )
            return {**result, "receiptPath": str(receipt)}
        except Exception as e:
            receipt = write_action_receipt(
                action="voice_speak",
                mission_id="voice-speak",
                mission_title=f"Speak: {text[:60]}",
                status="failed",
                target_agent="none",
                target_lane="voice-tts",
                authority="operator",
                payload={**receipt_payload, "error": str(e)},
                next_action="no TTS available",
            )
            return {"ok": False, "error": str(e), "provider": "none", "receiptPath": str(receipt)}

    def _speak_elevenlabs(self, text: str, voice_id: str) -> Dict[str, Any]:
        """Call ElevenLabs API and play audio via aplay."""
        url = f"{ELEVENLABS_API_URL}/{voice_id}"
        payload = json.dumps({
            "text": text,
            "model_id": ELEVENLABS_MODEL,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self._api_key,
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_data = resp.read()

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(audio_data)
        tmp.close()
        self._last_audio_path = tmp.name
        self._last_provider = "elevenlabs"

        # Play with aplay (mp3 is supported by most modern aplay via libsndfile)
        # If aplay fails, try ffplay or just note the file path
        try:
            subprocess.run(
                ["aplay", tmp.name],
                capture_output=True,
                timeout=60,
                check=True,
            )
            played = True
        except Exception as play_err:
            # aplay may not support mp3 — try converting or just save file
            played = False
            play_err_str = str(play_err)

        return {
            "ok": True,
            "provider": "elevenlabs",
            "voiceId": voice_id,
            "audioPath": tmp.name,
            "audioBytes": len(audio_data),
            "played": played,
            "playError": play_err_str if not played else None,
        }

    def _speak_espeak(self, text: str) -> Dict[str, Any]:
        """Speak via espeak-ng → aplay."""
        # Generate WAV
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        self._last_audio_path = tmp.name
        self._last_provider = "espeak-ng"

        subprocess.run(
            ["espeak-ng", "-v", "en-us+f3", "-s", "175", text, "-w", tmp.name],
            capture_output=True,
            timeout=30,
            check=True,
        )

        # Play
        subprocess.run(
            ["aplay", tmp.name],
            capture_output=True,
            timeout=60,
            check=True,
        )

        return {
            "ok": True,
            "provider": "espeak-ng",
            "audioPath": tmp.name,
            "played": True,
        }


# Singleton
_speak_service: Optional[VoiceSpeakService] = None


def get_voice_speak_service() -> VoiceSpeakService:
    global _speak_service
    if _speak_service is None:
        _speak_service = VoiceSpeakService()
    return _speak_service
