#!/usr/bin/env python3
"""
MOS Cockpit page for the Phase2C review build.

Closed-loop operator surface over the existing MOS ingress/authority spine.
This page owns no service authority and has one controlled emit only.
"""

from __future__ import annotations

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib

from services import mos_cockpit_service as cockpit


class MOSCockpitPage(Gtk.ScrolledWindow):
    """Operator cockpit for MOS state, ingress events, results, and one safe emit."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._last_snapshot: dict = {}
        self._poll_source_id = 0

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(header)

        title = Gtk.Label(label="MOS Cockpit")
        title.add_css_class("title-1")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)

        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh(include_provider=True))
        header.append(refresh)

        emit = Gtk.Button(label="Roxy Status Query")
        emit.add_css_class("suggested-action")
        emit.connect("clicked", self._on_emit_clicked)
        header.append(emit)

        self.summary = Gtk.Label()
        self.summary.set_xalign(0)
        self.summary.set_wrap(True)
        self.summary.add_css_class("caption")
        main_box.append(self.summary)

        token_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_box.append(token_row)
        token_label = Gtk.Label(label="Ingress token")
        token_label.set_xalign(0)
        token_row.append(token_label)
        self.token_entry = Gtk.Entry()
        self.token_entry.set_visibility(False)
        self.token_entry.set_placeholder_text("session-only; never written to disk")
        self.token_entry.set_hexpand(True)
        token_row.append(self.token_entry)

        preview_label = Gtk.Label(label="Payload Preview")
        preview_label.add_css_class("title-3")
        preview_label.set_xalign(0)
        main_box.append(preview_label)

        self.payload_view = Gtk.TextView()
        self.payload_view.set_editable(False)
        self.payload_view.set_monospace(True)
        self.payload_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.payload_view.set_size_request(-1, 120)
        main_box.append(self.payload_view)

        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_monospace(True)
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        main_box.append(self.text)

        self._set_payload_preview()
        self.refresh(include_provider=True)
        self._poll_source_id = GLib.timeout_add_seconds(2, self._poll_recent)

    def _token(self) -> str:
        return self.token_entry.get_text().strip()

    def _set_payload_preview(self):
        self.payload_view.get_buffer().set_text(json.dumps(cockpit.controlled_roxy_status_payload(), indent=2))

    def refresh(self, *, include_provider: bool = False):
        try:
            data = cockpit.snapshot(self._token(), include_provider=include_provider)
            if not include_provider and self._last_snapshot.get("roxyStatus"):
                data["roxyStatus"] = self._last_snapshot["roxyStatus"]
            self._last_snapshot = data
            self.summary.set_label(
                "Single-throat MOS cockpit. Reads existing status and emits only the previewed DeviceInputEvent."
            )
            self.text.get_buffer().set_text(self._format(data))
        except Exception as exc:
            self.summary.set_label("Cockpit snapshot failed. No mutation was attempted.")
            self.text.get_buffer().set_text(f"MOS Cockpit snapshot failed: {exc}")

    def _poll_recent(self) -> bool:
        self.refresh(include_provider=False)
        return True

    def _on_emit_clicked(self, *_):
        try:
            result = cockpit.send_roxy_status_query(self._token())
            self.summary.set_label(
                f"Roxy Status Query sent via {result.get('route')}; response status={result.get('response', {}).get('status')}"
            )
            self.refresh(include_provider=False)
        except Exception as exc:
            self.summary.set_label(f"Roxy Status Query failed: {exc}")
            self.refresh(include_provider=False)

    def _format(self, data: dict) -> str:
        lines: list[str] = []
        lines.append(f"generatedAt: {data.get('generatedAt', '')}")
        lines.append("")

        ingress = data.get("ingress", {})
        ingress_health = ingress.get("health", {})
        ingress_data = ingress_health.get("data", {}) if isinstance(ingress_health.get("data"), dict) else {}
        lines.append("route / service status:")
        lines.append(f"  ingress health: {self._state(ingress_health)} {ingress_health.get('url', '')}")
        lines.append(f"  token required: {ingress_data.get('tokenRequired')}")
        lines.append(f"  stream clients: {ingress_data.get('clients')}")
        lines.append(f"  authority health: {self._state(data.get('authority', {}).get('health', {}))}")
        for name, route in ingress.get("routeStatus", {}).items():
            lines.append(f"  {name}: {route}")
        listeners = data.get("listeners", "")
        lines.append("  listeners:")
        if listeners:
            for line in listeners.splitlines():
                lines.append(f"    {line}")
        else:
            lines.append("    no 49170/49172/49173/9135/19135 listeners observed")
        lines.append("")

        lines.append("event monitor:")
        events = ingress.get("events", {})
        if not events.get("ok"):
            lines.append(f"  ingress stream offline or unauthorized: {events.get('error') or events.get('bodySummary')}")
        for event in events.get("data", {}).get("events", [])[:12]:
            lines.append(
                "  "
                f"{event.get('createdAt')} {event.get('route')} "
                f"status={event.get('status')} routed={event.get('routed')} suppressed={event.get('suppressed')} "
                f"eventId={event.get('eventId')} device={event.get('deviceId')} signal={event.get('signalId')} "
                f"action={event.get('actionId')} target={event.get('target')} reason={event.get('reason')}"
            )
        lines.append("")

        lines.append("result ledger:")
        results = ingress.get("results", {})
        if not results.get("ok"):
            lines.append(f"  ingress result ledger offline or unauthorized: {results.get('error') or results.get('bodySummary')}")
        for result in results.get("data", {}).get("results", [])[:12]:
            lines.append(
                "  "
                f"{result.get('createdAt')} source={result.get('source')} op={result.get('operation')} "
                f"success={result.get('success')} eventId={result.get('eventId')} action={result.get('actionId')} "
                f"target={result.get('target')} reason={result.get('failureReason')}"
            )
        local = data.get("localLedger", {})
        for result in local.get("entries", [])[:8]:
            lines.append(
                "  local "
                f"{result.get('createdAt')} route={result.get('route')} status={result.get('responseStatus')} "
                f"success={result.get('success')} eventId={result.get('eventId')}"
            )
        lines.append(f"  local ledger path: {local.get('path')}")
        lines.append("")

        lines.append("profile / binding browser:")
        authority = data.get("authority", {})
        bindings = authority.get("bindings", {})
        binding_data = bindings.get("data", {}) if isinstance(bindings.get("data"), dict) else {}
        profiles = binding_data.get("profiles") if isinstance(binding_data.get("profiles"), list) else []
        flat_bindings = binding_data.get("bindings") if isinstance(binding_data.get("bindings"), list) else []
        lines.append(f"  route: {bindings.get('route')} state={self._state(bindings)}")
        lines.append(f"  activeProfileId: {binding_data.get('activeProfileId')}")
        lines.append(f"  profile count: {len(profiles)} flat binding count: {len(flat_bindings)}")
        for profile in profiles[:8]:
            profile_bindings = profile.get("bindings") if isinstance(profile.get("bindings"), list) else []
            lines.append(f"  profile {profile.get('id')}: {profile.get('name')} bindings={len(profile_bindings)}")
            for binding in profile_bindings[:6]:
                action = binding.get("action") or {}
                macro = binding.get("macro") if isinstance(binding.get("macro"), list) else []
                op = action.get("op") or (macro[0].get("op") if macro else "")
                target = action.get("target") or (macro[0].get("target") if macro else "local")
                lines.append(f"    {binding.get('label')}: source={binding.get('source')} op={op} target={target}")
        lines.append("")

        roxy = data.get("roxyStatus", {})
        surfaces = roxy.get("control_surfaces", {})
        lines.append("control surface dashboard:")
        for device_id, item in surfaces.get("devices", {}).items():
            lines.append(
                f"  {device_id}: {item.get('statusTier')} "
                f"usbPresent={item.get('usbPresent')} byIdPresent={item.get('byIdPresent')} "
                f"dryRun={item.get('dryRunProven')} liveReady={item.get('liveCaptureReady')} "
                f"liveProven={item.get('liveCaptureProven')} routed={item.get('routedProven')}"
            )
            if item.get("note"):
                lines.append(f"    note: {item.get('note')}")
        lines.append("")

        skybeam = roxy.get("skybeam", {})
        event_policy = skybeam.get("event_policy", {})
        lines.append("skybeam / obs:")
        lines.append(f"  root: {skybeam.get('root')} exists={skybeam.get('exists')}")
        lines.append(f"  latest meta: {skybeam.get('latest_meta', {}).get('path')}")
        lines.append(f"  latest recording: {skybeam.get('latest_recording', {}).get('path')}")
        lines.append(f"  obs listener probe: {skybeam.get('obs_listener_probe') or 'none'}")
        lines.append(
            f"  event policy: status={event_policy.get('status')} "
            f"deviceId={event_policy.get('deviceId')} route={event_policy.get('route')}"
        )
        lines.append("")

        lines.append("guardrails:")
        for warning in roxy.get("warnings", []):
            lines.append(f"  - {warning}")
        lines.append("  - This page does not start services, remount drives, or replace the live baseline.")

        return "\n".join(lines)

    @staticmethod
    def _state(item: dict) -> str:
        return "OK" if item.get("ok") else "WARN"
