#!/usr/bin/env python3
"""
Voice / Actions Page — Voice Operator panel with RCC-backed conversational Roxy.

- Voice Foundry status (primary TTS)
- Ask Roxy (text → brain → Voice Foundry)
- Speak Text (direct TTS)
- Push-to-Talk (record → STT → brain → voice)
- Wake service status
- Last interaction display
- Command receipts
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
from services.voice_operator_service import get_voice_operator_service
from services.rcc_adapter import RCCAdapter


class VoiceActionsPage(Gtk.ScrolledWindow):
    """Voice Operator panel — RCC-backed, thin GTK4 shell."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._voice_svc = get_voice_command_service()
        self._op_svc = get_voice_operator_service()
        self._rcc = RCCAdapter()
        self._recording = False
        self._build_ui()
        GLib.timeout_add_seconds(5, self._periodic_refresh)

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Voice Operator")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Voice Foundry Status Card
        self._build_voice_status_card(main_box)

        # Ask Roxy Card
        self._build_ask_roxy_card(main_box)

        # Speak Text Card
        self._build_speak_text_card(main_box)

        # Wake Service Status Card
        self._build_wake_status_card(main_box)

        # Last Interaction Card
        self._build_last_interaction_card(main_box)

        # Push-to-talk section
        self._build_ptt_section(main_box)

        # Command log section
        self._build_command_log_section(main_box)

        # Receipts section
        self._build_receipts_section(main_box)

    def _build_voice_status_card(self, parent):
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

    def _build_ask_roxy_card(self, parent):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        title = Gtk.Label(label="Ask Roxy")
        title.add_css_class("title-3")
        title.set_xalign(0)
        card.append(title)

        sub = Gtk.Label(label="Type a question. Roxy answers from live estate context via Voice Foundry.")
        sub.add_css_class("caption")
        sub.set_xalign(0)
        sub.set_wrap(True)
        card.append(sub)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(8)
        card.append(row)

        self._ask_entry = Gtk.Entry()
        self._ask_entry.set_placeholder_text('e.g. "What are our squads doing?"')
        self._ask_entry.set_hexpand(True)
        self._ask_entry.connect("activate", self._on_ask_roxy)
        row.append(self._ask_entry)

        ask_btn = Gtk.Button(label="🧠 Ask")
        ask_btn.add_css_class("suggested-action")
        ask_btn.connect("clicked", self._on_ask_roxy)
        row.append(ask_btn)

        self._ask_status = Gtk.Label(label="Ready")
        self._ask_status.add_css_class("caption")
        self._ask_status.set_xalign(0)
        card.append(self._ask_status)

    def _build_speak_text_card(self, parent):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        title = Gtk.Label(label="Speak Text")
        title.add_css_class("title-3")
        title.set_xalign(0)
        card.append(title)

        sub = Gtk.Label(label="Speak directly through Voice Foundry (no brain).")
        sub.add_css_class("caption")
        sub.set_xalign(0)
        sub.set_wrap(True)
        card.append(sub)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(8)
        card.append(row)

        self._speak_entry = Gtk.Entry()
        self._speak_entry.set_placeholder_text("Type text to speak aloud...")
        self._speak_entry.set_hexpand(True)
        self._speak_entry.connect("activate", self._on_speak_text)
        row.append(self._speak_entry)

        speak_btn = Gtk.Button(label="🔊 Speak")
        speak_btn.add_css_class("suggested-action")
        speak_btn.connect("clicked", self._on_speak_text)
        row.append(speak_btn)

        self._speak_status = Gtk.Label(label="Ready")
        self._speak_status.add_css_class("caption")
        self._speak_status.set_xalign(0)
        card.append(self._speak_status)

    def _build_wake_status_card(self, parent):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        title = Gtk.Label(label="Wake Service")
        title.add_css_class("title-3")
        title.set_xalign(0)
        card.append(title)

        self._wake_status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._wake_status_box.set_margin_start(8)
        card.append(self._wake_status_box)

        self._update_wake_status()

    def _build_last_interaction_card(self, parent):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)
        card.add_css_class("card")
        parent.append(card)

        title = Gtk.Label(label="Last Interaction")
        title.add_css_class("title-3")
        title.set_xalign(0)
        card.append(title)

        self._last_transcript_lbl = Gtk.Label(label="Transcript: —")
        self._last_transcript_lbl.add_css_class("caption")
        self._last_transcript_lbl.set_xalign(0)
        self._last_transcript_lbl.set_wrap(True)
        card.append(self._last_transcript_lbl)

        self._last_response_lbl = Gtk.Label(label="Response: —")
        self._last_response_lbl.add_css_class("caption")
        self._last_response_lbl.set_xalign(0)
        self._last_response_lbl.set_wrap(True)
        card.append(self._last_response_lbl)

        self._last_audio_lbl = Gtk.Label(label="Audio: —")
        self._last_audio_lbl.add_css_class("caption")
        self._last_audio_lbl.set_xalign(0)
        card.append(self._last_audio_lbl)

        open_btn = Gtk.Button(label="📂 Open Last Receipt")
        open_btn.add_css_class("pill")
        open_btn.set_margin_top(8)
        open_btn.connect("clicked", self._on_open_last_receipt)
        card.append(open_btn)

    def _build_ptt_section(self, parent):
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
        log_title = Gtk.Label(label="Command Log")
        log_title.add_css_class("title-3")
        log_title.set_xalign(0)
        log_title.set_margin_top(8)
        parent.append(log_title)

        self._log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        parent.append(self._log_box)

    def _build_receipts_section(self, parent):
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
        self._update_wake_status()

    def _on_ask_roxy(self, button_or_entry):
        text = self._ask_entry.get_text().strip()
        if not text:
            self._ask_status.set_label("Enter a question first")
            return
        self._ask_status.set_label("🧠 Thinking...")

        def _do_ask():
            try:
                result = self._op_svc.ask(text)
                GLib.idle_add(self._ask_finished, result)
            except Exception as e:
                GLib.idle_add(self._ask_status.set_label, f"❌ Error: {e}")

        import threading
        threading.Thread(target=_do_ask, daemon=True).start()

    def _ask_finished(self, result: dict):
        if result.get("ok"):
            response = result.get("response", "")
            self._ask_status.set_label(f"✅ {response[:80]}...")
            self._update_last_interaction()
            self._add_log_entry(result.get("transcript", ""), "ask", response)
        else:
            self._ask_status.set_label(f"❌ {result.get('error', 'Failed')}")
        return False

    def _on_speak_text(self, button_or_entry):
        text = self._speak_entry.get_text().strip()
        if not text:
            self._speak_status.set_label("Enter text to speak")
            return
        self._speak_status.set_label("🔊 Rendering voice...")

        def _do_speak():
            try:
                result = self._op_svc.speak(text)
                GLib.idle_add(self._speak_status.set_label,
                    "✅ Spoken via Voice Foundry" if result.get("ok") else f"❌ {result.get('error', 'Failed')}")
            except Exception as e:
                GLib.idle_add(self._speak_status.set_label, f"❌ Error: {e}")

        import threading
        threading.Thread(target=_do_speak, daemon=True).start()

    def _on_open_last_receipt(self, button):
        last = self._op_svc.get_last_interaction().get("receiptPath")
        if last and Path(last).exists():
            self._speak_status.set_label(f"📂 {last}")
        else:
            # Fallback: look for latest SSOT receipt
            receipt_dir = Path("/mnt/work/ssot/mindsong-juke-hub/output/voice/roxy-wake")
            if receipt_dir.exists():
                files = sorted(receipt_dir.glob("roxy-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    self._speak_status.set_label(f"📂 {files[0]}")
                else:
                    self._speak_status.set_label("No receipts found")
            else:
                self._speak_status.set_label("No receipts found")

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

    def _update_voice_status(self):
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
            for cls in ["status-healthy", "status-warn", "status-blocked"]:
                self._voice_status_label.remove_css_class(cls)
            self._voice_status_label.add_css_class(color_class)

            while self._voice_detail_box.get_first_child():
                self._voice_detail_box.remove(self._voice_detail_box.get_first_child())

            for svc_name, svc_info in status.get("services", {}).items():
                alive = "🟢" if svc_info.get("alive") else "🔴"
                port = svc_info.get("port", "?")
                role = svc_info.get("role", "")
                lbl = Gtk.Label(label=f"{alive} {svc_name} (:{port}) {role}")
                lbl.add_css_class("moc-row-subtitle")
                lbl.set_xalign(0)
                self._voice_detail_box.append(lbl)

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

    def _update_wake_status(self):
        while self._wake_status_box.get_first_child():
            self._wake_status_box.remove(self._wake_status_box.get_first_child())

        try:
            result = self._rcc.run("voice.wake-status", json_output=True)
            if result.ok and result.data:
                cfg = result.data.get("config", {})
                svc = result.data.get("service", {})
                active = svc.get("active", False)
                enabled = svc.get("enabled", False)

                wake_lbl = Gtk.Label(label=f"🎯 Wake phrase: '{cfg.get('wakeWord', 'unknown')}'")
                wake_lbl.add_css_class("moc-row-subtitle")
                wake_lbl.set_xalign(0)
                self._wake_status_box.append(wake_lbl)

                voice_lbl = Gtk.Label(label=f"🎤 Voice: {cfg.get('voice', 'unknown')} ({cfg.get('provider', 'unknown')})")
                voice_lbl.add_css_class("moc-row-subtitle")
                voice_lbl.set_xalign(0)
                self._wake_status_box.append(voice_lbl)

                state_icon = "🟢" if active else "🔴"
                state_lbl = Gtk.Label(label=f"{state_icon} Service: {svc.get('state', 'unknown')} (enabled: {enabled})")
                state_lbl.add_css_class("moc-row-subtitle")
                state_lbl.set_xalign(0)
                self._wake_status_box.append(state_lbl)

                note = result.data.get("note", "")
                if note:
                    note_lbl = Gtk.Label(label=f"ℹ️ {note}")
                    note_lbl.add_css_class("caption")
                    note_lbl.set_xalign(0)
                    note_lbl.set_wrap(True)
                    self._wake_status_box.append(note_lbl)
            else:
                err = Gtk.Label(label="⚠️ Could not read wake status from RCC")
                err.add_css_class("caption")
                err.set_xalign(0)
                self._wake_status_box.append(err)
        except Exception as e:
            err = Gtk.Label(label=f"⚠️ Wake status error: {e}")
            err.add_css_class("caption")
            err.set_xalign(0)
            self._wake_status_box.append(err)

    def _update_last_interaction(self):
        last = self._op_svc.get_last_interaction()
        self._last_transcript_lbl.set_label(f"Transcript: {last.get('transcript') or '—'}")
        self._last_response_lbl.set_label(f"Response: {last.get('response') or '—'}")
        self._last_audio_lbl.set_label(f"Audio: {last.get('audioPath') or '—'}")

    def _add_log_entry(self, transcript: str, action: str, response: str):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        icon = {"status": "📊", "judge": "⚖️", "kimi": "🤖", "investigate": "🔍", "ask": "🧠", "speak": "🔊"}.get(action, "🎙")
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"{icon} [{ts}] '{transcript[:50]}' → {action}: {response[:80]}"

        lbl = Gtk.Label(label=text)
        lbl.add_css_class("caption")
        lbl.set_xalign(0)
        lbl.set_wrap(True)
        lbl.set_hexpand(True)
        row.append(lbl)

        self._log_box.prepend(row)

        child = self._log_box.get_last_child()
        count = 0
        while child:
            count += 1
            child = child.get_prev_sibling()
        if count > 10:
            oldest = self._log_box.get_last_child()
            if oldest:
                self._log_box.remove(oldest)

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

    def _periodic_refresh(self):
        if not self.get_mapped():
            return True
        self._update_voice_status()
        self._update_wake_status()
        return True

    def update(self, data: dict):
        if not self.get_mapped():
            return
        self._update_voice_status()
        self._update_wake_status()
        self._update_voice_receipts()
