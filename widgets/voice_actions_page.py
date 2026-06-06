#!/usr/bin/env python3
"""
Voice / Actions Page — Action pipeline visibility + push-to-talk.

Reads Voice Foundry status, shows push-to-talk controls, displays
voice command receipts from output/roxy-command-center/actions/.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List
import json
from pathlib import Path
from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.voice_status_provider import get_voice_status
from services.voice_command_service import get_voice_command_service


class VoiceActionsPage(Gtk.ScrolledWindow):
    """Action pipeline and voice command visibility."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._voice_svc = get_voice_command_service()
        self._recording = False
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Voice / Actions")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Voice Foundry Status Card
        self._build_voice_status_card(main_box)

        # TTS Status Card
        self._build_tts_status_card(main_box)

        # Push-to-talk section
        self._build_ptt_section(main_box)

        # Command log section
        self._build_command_log_section(main_box)

        # Receipts section
        self._build_receipts_section(main_box)

    def _build_voice_status_card(self, parent):
        """Build the Voice Foundry status card."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.append(header)

        self._voice_status_label = Gtk.Label(label="Voice Foundry: checking...")
        self._voice_status_label.add_css_class("title-3")
        self._voice_status_label.set_xalign(0)
        self._voice_status_label.set_hexpand(True)
        header.append(self._voice_status_label)

        refresh_btn = Gtk.Button(label="🔄 Refresh")
        refresh_btn.add_css_class("pill")
        refresh_btn.add_css_class("caption")
        refresh_btn.connect("clicked", self._on_refresh_status)
        header.append(refresh_btn)

        self._voice_detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._voice_detail_box.set_margin_start(8)
        card.append(self._voice_detail_box)

        self._update_voice_status()

    def _build_tts_status_card(self, parent):
        """TTS capability status."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card.append(header)

        title = Gtk.Label(label="Text-to-Speech")
        title.add_css_class("title-3")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)

        detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        detail.set_margin_start(8)
        card.append(detail)

        try:
            from services.voice_speak_service import get_voice_speak_service
            svc = get_voice_speak_service()
            if svc._api_key:
                lbl = Gtk.Label(label="🟢 ElevenLabs (Jessica) — API key present")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                detail.append(lbl)
            else:
                lbl = Gtk.Label(label="🔴 ElevenLabs — API key missing")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                detail.append(lbl)

            if svc._espeak_available():
                lbl = Gtk.Label(label="🟢 espeak-ng — local fallback available")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                detail.append(lbl)
            else:
                lbl = Gtk.Label(label="🔴 espeak-ng — not installed")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                detail.append(lbl)

            # Test speak row
            test_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            test_box.set_margin_top(8)
            detail.append(test_box)

            self._speak_entry = Gtk.Entry()
            self._speak_entry.set_placeholder_text("Type text to speak aloud...")
            self._speak_entry.set_hexpand(True)
            test_box.append(self._speak_entry)

            speak_btn = Gtk.Button(label="🔊 Speak")
            speak_btn.add_css_class("suggested-action")
            speak_btn.connect("clicked", self._on_test_speak)
            test_box.append(speak_btn)
        except Exception as e:
            err = Gtk.Label(label=f"⚠️ TTS check error: {e}")
            err.add_css_class("caption")
            err.set_xalign(0)
            detail.append(err)

    def _build_ptt_section(self, parent):
        """Push-to-talk controls."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        ptt_title = Gtk.Label(label="Push-to-Talk")
        ptt_title.add_css_class("title-3")
        ptt_title.set_xalign(0)
        card.append(ptt_title)

        ptt_sub = Gtk.Label(label="Hold to speak, release to transcribe. Commands: status, ask the judge, assign Kimi, investigate.")
        ptt_sub.add_css_class("caption")
        ptt_sub.set_xalign(0)
        ptt_sub.set_wrap(True)
        card.append(ptt_sub)

        self._ptt_button = Gtk.Button(label="🎙 Hold to Speak")
        self._ptt_button.add_css_class("suggested-action")
        self._ptt_button.set_size_request(-1, 48)
        # GTK gesture for press/release
        press = Gtk.GestureClick()
        press.connect("pressed", self._on_ptt_pressed)
        press.connect("released", self._on_ptt_released)
        self._ptt_button.add_controller(press)
        card.append(self._ptt_button)

        self._ptt_status = Gtk.Label(label="Ready")
        self._ptt_status.add_css_class("caption")
        self._ptt_status.set_xalign(0)
        card.append(self._ptt_status)

    def _build_command_log_section(self, parent):
        """Command log."""
        log_title = Gtk.Label(label="Command Log")
        log_title.add_css_class("title-3")
        log_title.set_xalign(0)
        log_title.set_margin_top(8)
        parent.append(log_title)

        self._log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        parent.append(self._log_box)

    def _build_receipts_section(self, parent):
        """Receipts section."""
        receipts_title = Gtk.Label(label="Recent Voice Receipts")
        receipts_title.add_css_class("title-3")
        receipts_title.set_xalign(0)
        receipts_title.set_margin_top(8)
        parent.append(receipts_title)

        self._stats_label = Gtk.Label(label="")
        self._stats_label.add_css_class("caption")
        self._stats_label.set_xalign(0)
        parent.append(self._stats_label)

        self._rows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        parent.append(self._rows_box)

    def _on_refresh_status(self, button):
        self._update_voice_status()

    def _on_ptt_pressed(self, gesture, n_press, x, y):
        self._recording = True
        self._ptt_button.set_label("🔴 Recording...")
        self._ptt_status.set_label("Recording — speak now")
        try:
            result = self._voice_svc.start_recording()
            if not result.get("ok"):
                self._ptt_status.set_label(f"Start failed: {result.get('error', 'unknown')}")
                self._recording = False
                self._ptt_button.set_label("🎙 Hold to Speak")
        except Exception as e:
            self._ptt_status.set_label(f"Start error: {e}")
            self._recording = False
            self._ptt_button.set_label("🎙 Hold to Speak")

    def _on_ptt_released(self, gesture, n_press, x, y):
        if not self._recording:
            return
        self._recording = False
        self._ptt_button.set_label("⏳ Transcribing...")
        self._ptt_status.set_label("Transcribing...")

        try:
            result = self._voice_svc.stop_recording()
            if not result.get("ok"):
                self._ptt_status.set_label(f"Stop failed: {result.get('error', 'unknown')}")
                self._ptt_button.set_label("🎙 Hold to Speak")
                return

            if not result.get("routed"):
                reason = result.get("reason", "no speech")
                self._ptt_status.set_label(f"No command: {reason}")
                self._ptt_button.set_label("🎙 Hold to Speak")
                return

            transcript = result.get("transcript", "")
            routed = result.get("action", "unknown")
            response = result.get("response", "")
            receipt = result.get("receiptPath", "")

            self._ptt_status.set_label(f"🔊 Heard: '{transcript}' → {routed}")
            self._add_log_entry(transcript, routed, response)
            self._update_voice_receipts()

        except Exception as e:
            self._ptt_status.set_label(f"Stop error: {e}")
        finally:
            self._ptt_button.set_label("🎙 Hold to Speak")

    def _on_test_speak(self, button):
        """Test TTS: speak the entry text aloud."""
        text = self._speak_entry.get_text().strip()
        if not text:
            self._ptt_status.set_label("Enter text to speak")
            return
        self._ptt_status.set_label(f"🔊 Speaking: '{text[:40]}...'")
        try:
            from services.voice_speak_service import get_voice_speak_service
            svc = get_voice_speak_service()
            result = svc.speak(text, source="test-button")
            provider = result.get("provider", "unknown")
            self._ptt_status.set_label(f"✅ Spoken via {provider}: '{text[:40]}...'")
        except Exception as e:
            self._ptt_status.set_label(f"❌ Speak failed: {e}")

    def _add_log_entry(self, transcript: str, action: str, response: str):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        icon = {"status": "📊", "judge": "⚖️", "kimi": "🤖", "investigate": "🔍"}.get(action, "🎙")
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"{icon} [{ts}] '{transcript[:50]}' → {action}: {response[:80]}"

        lbl = Gtk.Label(label=text)
        lbl.add_css_class("caption")
        lbl.set_xalign(0)
        lbl.set_wrap(True)
        lbl.set_hexpand(True)
        row.append(lbl)

        self._log_box.prepend(row)

        # Trim log to last 10 entries
        child = self._log_box.get_last_child()
        count = 0
        while child:
            count += 1
            child = child.get_prev_sibling()
        if count > 10:
            # Remove oldest
            oldest = self._log_box.get_last_child()
            if oldest:
                self._log_box.remove(oldest)

    def _update_voice_status(self):
        """Update Voice Foundry status display."""
        try:
            status = get_voice_status()
            classification = status.get("classification", "UNKNOWN")

            color_class = {
                "READY": "status-healthy",
                "PARTIAL": "status-warn",
                "DORMANT": "status-warn",
                "MISSING_SERVICE": "status-blocked",
                "PATH_ISSUE": "status-blocked",
                "BLOCKED": "status-blocked",
            }.get(classification, "status-warn")

            self._voice_status_label.set_label(f"Voice Foundry: {classification}")
            # Remove old color classes first
            for cls in ["status-healthy", "status-warn", "status-blocked"]:
                self._voice_status_label.remove_css_class(cls)
            self._voice_status_label.add_css_class(color_class)

            # Clear details
            while self._voice_detail_box.get_first_child():
                self._voice_detail_box.remove(self._voice_detail_box.get_first_child())

            # Service details
            for svc_name, svc_info in status.get("services", {}).items():
                alive = "🟢" if svc_info.get("alive") else "🔴"
                port = svc_info.get("port", "?")
                role = svc_info.get("role", "")
                lbl = Gtk.Label(label=f"{alive} {svc_name} (:{port}) {role}")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                self._voice_detail_box.append(lbl)

            # Blocker / recommendation
            if status.get("blocker"):
                blocker_lbl = Gtk.Label(label=f"⚠️ {status['blocker']}")
                blocker_lbl.add_css_class("caption")
                blocker_lbl.add_css_class("status-blocked-text")
                blocker_lbl.set_xalign(0)
                blocker_lbl.set_wrap(True)
                self._voice_detail_box.append(blocker_lbl)

            if status.get("recommendation"):
                rec_lbl = Gtk.Label(label=f"💡 {status['recommendation']}")
                rec_lbl.add_css_class("caption")
                rec_lbl.set_xalign(0)
                rec_lbl.set_wrap(True)
                self._voice_detail_box.append(rec_lbl)

        except Exception as exc:
            self._voice_status_label.set_label(f"Voice Foundry: ERROR ({exc})")

    def _read_voice_receipts(self) -> List[dict]:
        try:
            receipt_dir = Path(__file__).parent.parent / "output" / "roxy-command-center" / "actions"
            if not receipt_dir.exists():
                return []
            files = sorted(receipt_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            receipts = []
            for f in files[:20]:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("action", "").startswith("voice_"):
                        receipts.append(data)
                except Exception:
                    pass
            return receipts
        except Exception:
            return []

    def _update_voice_receipts(self):
        receipts = self._read_voice_receipts()

        self._stats_label.set_label(f"Last {len(receipts)} voice receipts")

        while self._rows_box.get_first_child():
            self._rows_box.remove(self._rows_box.get_first_child())

        for receipt in receipts:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_top(2)
            row.set_margin_bottom(2)

            action = receipt.get("action", "?").replace("voice_", "")
            status = receipt.get("status", "?")
            title = receipt.get("missionTitle", "")
            ts = receipt.get("requestedAt", "")[:19]

            icon = {"status": "📊", "judge": "⚖️", "kimi": "🤖", "investigate": "🔍"}.get(action, "🎙")
            text = f"{icon} {ts} · {action} · {title[:50]}"

            lbl = Gtk.Label(label=text)
            lbl.add_css_class("caption")
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            row.append(lbl)
            self._rows_box.append(row)

    def update(self, data: dict):
        self._update_voice_status()
        self._update_voice_receipts()
