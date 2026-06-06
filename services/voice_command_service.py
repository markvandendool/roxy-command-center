#!/usr/bin/env python3
"""
Voice Command Service — Push-to-talk operator commands.

Wires the dictation daemon (:10500) to Roxy Command Center actions:
- "Roxy, status" → civilization health summary
- "Roxy, ask the judge" → async Judge review of selected mission
- "Roxy, assign Kimi" → Kimi assignment for selected mission
- "Roxy, investigate" → investigation packet for selected mission

Every voice command writes an action receipt.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from services.action_receipt_service import write_action_receipt
from services.judge_service import get_judge_service
from services.kimi_assignment_service import create_assignment_packet
from services.investigation_service import create_investigation_packet
from services.voice_speak_service import get_voice_speak_service

DICTATION_URL = "http://127.0.0.1:10500"


def _ts() -> str:
    return datetime.now().isoformat()


def _post(path: str) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(
            f"{DICTATION_URL}{path}",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class VoiceCommandService:
    """Push-to-talk voice command handler."""

    def __init__(self):
        self._recording = False
        self._last_transcript: Optional[str] = None
        self._last_receipt: Optional[Path] = None

    def start_recording(self) -> Dict[str, Any]:
        """Begin push-to-talk recording."""
        result = _post("/dictate/start")
        self._recording = result.get("ok", False)
        return result

    def stop_recording(self) -> Dict[str, Any]:
        """Stop recording, get transcript, route to action."""
        result = _post("/dictate/stop")
        self._recording = False
        if not result.get("ok"):
            return result

        transcript = result.get("transcript", "").strip()
        self._last_transcript = transcript

        if not transcript:
            return {**result, "routed": False, "reason": "empty transcript"}

        routed = self._route_transcript(transcript)
        # Flatten routed action result into top-level keys so UI can read
        # action, response, receiptPath as simple strings
        merged = {**result, "routed": True}
        merged.update(routed)
        return merged

    def toggle_recording(self) -> Dict[str, Any]:
        """Toggle recording state."""
        if self._recording:
            return self.stop_recording()
        return self.start_recording()

    def _route_transcript(self, transcript: str) -> Dict[str, Any]:
        """Route a transcript to the appropriate action."""
        t = transcript.lower()

        # Status command
        if any(k in t for k in ["status", "how are you", "what's the status", "whats the status", "health"]):
            return self._do_status_command(transcript)

        # Judge command
        if any(k in t for k in ["judge", "review", "critique"]):
            return self._do_judge_command(transcript)

        # Kimi command
        if any(k in t for k in ["kimi", "assign"]):
            return self._do_kimi_command(transcript)

        # Investigate command
        if any(k in t for k in ["investigate", "look into", "dig into"]):
            return self._do_investigate_command(transcript)

        # Unknown
        return self._do_unknown_command(transcript)

    def _speak_and_receipt(self, action: str, transcript: str, response: str, payload: Dict[str, Any]) -> Path:
        """Speak response aloud (async) and write action receipt."""
        # Fire speak async so GTK UI doesn't freeze during API call + playback
        def _do_speak():
            try:
                speak_svc = get_voice_speak_service()
                speak_svc.speak(response, source=f"voice-{action}")
            except Exception:
                pass  # Speak errors are non-fatal; speak service writes its own receipt

        import threading
        threading.Thread(target=_do_speak, daemon=True).start()

        receipt_path = write_action_receipt(
            action=f"voice_{action}",
            mission_id="voice-command",
            mission_title=f"Voice: {transcript[:80]}",
            status="completed",
            target_agent="roxy-voice",
            target_lane="voice-command",
            authority="operator",
            payload={**payload, "response": response, "speakInitiated": True},
            next_action="display response",
        )
        self._last_receipt = receipt_path
        return receipt_path

    def _do_status_command(self, transcript: str) -> Dict[str, Any]:
        from services.mission_truth_provider import MissionTruthProvider
        missions = MissionTruthProvider.get_missions()
        blocked = [m for m in missions if m.status.value == "blocked"]
        healthy = [m for m in missions if m.status.value == "healthy"]

        summary = (
            f"Roxy status: {len(missions)} missions, {len(healthy)} healthy, {len(blocked)} blocked. "
            f"Civilization is {'green' if not blocked else 'degraded'}."
        )

        receipt = self._speak_and_receipt("status", transcript, summary, {
            "transcript": transcript,
            "missionCount": len(missions),
            "healthyCount": len(healthy),
            "blockedCount": len(blocked),
            "response": summary,
        })

        return {"action": "status", "response": summary, "receiptPath": str(receipt)}

    def _do_judge_command(self, transcript: str) -> Dict[str, Any]:
        # For voice judge, we need a selected mission context.
        # Without UI selection, default to "current top blocked mission".
        from services.mission_truth_provider import MissionTruthProvider
        missions = MissionTruthProvider.get_missions()
        target = next((m for m in missions if m.status.value == "blocked"), missions[0] if missions else None)

        if not target:
            response = "No mission available to send to Judge."
            receipt = self._write_voice_receipt("judge", transcript, {"transcript": transcript, "error": "no mission"})
            return {"action": "judge", "response": response, "receiptPath": str(receipt)}

        prompt = (
            f"Mission: {target.name}\n"
            f"Status: {target.status.value}\n"
            f"Owner: {target.owner}\n"
            f"Blockers: {', '.join(target.blockers) or 'None'}\n\n"
            "Please perform an adversarial review. Identify errors, assumptions, gaps, or quality issues."
        )

        job = get_judge_service().submit_job(
            prompt=prompt,
            context=target.name,
            source_mission_id=target.id,
        )

        response = f"Sent mission '{target.name}' to Judge. Job {job.job_id} queued."
        receipt = self._speak_and_receipt("judge", transcript, response, {
            "transcript": transcript,
            "missionId": target.id,
            "missionName": target.name,
            "jobId": job.job_id,
            "response": response,
        })

        return {"action": "judge", "response": response, "jobId": job.job_id, "receiptPath": str(receipt)}

    def _do_kimi_command(self, transcript: str) -> Dict[str, Any]:
        from services.mission_truth_provider import MissionTruthProvider
        missions = MissionTruthProvider.get_missions()
        target = missions[0] if missions else None

        if not target:
            response = "No mission available to assign to Kimi."
            receipt = self._write_voice_receipt("kimi", transcript, {"transcript": transcript, "error": "no mission"})
            return {"action": "kimi", "response": response, "receiptPath": str(receipt)}

        result = create_assignment_packet(
            mission_id=target.id,
            mission_title=target.name,
            brief=f"Voice-assigned from Command Center. Transcript: {transcript}",
        )
        packet = result["packet"]

        response = f"Assigned mission '{target.name}' to Kimi on {packet['targetSurface']}."
        receipt = self._speak_and_receipt("kimi", transcript, response, {
            "transcript": transcript,
            "missionId": target.id,
            "missionName": target.name,
            "packetId": packet["packetId"],
            "targetSurface": packet["targetSurface"],
            "response": response,
        })

        return {"action": "kimi", "response": response, "packetId": packet["packetId"], "receiptPath": str(receipt)}

    def _do_investigate_command(self, transcript: str) -> Dict[str, Any]:
        from services.mission_truth_provider import MissionTruthProvider
        missions = MissionTruthProvider.get_missions()
        target = missions[0] if missions else None

        if not target:
            response = "No mission available to investigate."
            receipt = self._write_voice_receipt("investigate", transcript, {"transcript": transcript, "error": "no mission"})
            return {"action": "investigate", "response": response, "receiptPath": str(receipt)}

        result = create_investigation_packet(
            mission_id=target.id,
            mission_title=target.name,
            question=f"Voice request: {transcript}",
            source_artifacts=[target.data_source] if hasattr(target, "data_source") else [],
        )
        packet = result["packet"]

        response = f"Opened investigation for mission '{target.name}'."
        receipt = self._speak_and_receipt("investigate", transcript, response, {
            "transcript": transcript,
            "missionId": target.id,
            "missionName": target.name,
            "packetId": packet["packetId"],
            "response": response,
        })

        return {"action": "investigate", "response": response, "packetId": packet["packetId"], "receiptPath": str(receipt)}

    def _do_unknown_command(self, transcript: str) -> Dict[str, Any]:
        response = (
            f"I heard: '{transcript}'. Known commands: status, ask the judge, assign Kimi, investigate."
        )
        receipt = self._speak_and_receipt("unknown", transcript, response, {
            "transcript": transcript,
            "response": response,
        })
        return {"action": "unknown", "response": response, "receiptPath": str(receipt)}


# Singleton
_voice_service: Optional[VoiceCommandService] = None


def get_voice_command_service() -> VoiceCommandService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceCommandService()
    return _voice_service
