#!/usr/bin/env python3
"""
Read-only Roxy status page for the Phase 2C review build.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib

from services.roxy_status_provider import snapshot


class RoxyStatusPage(Gtk.ScrolledWindow):
    """Static/manual status view backed by the read-only status provider."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.append(header)

        title = Gtk.Label(label="Roxy Status")
        title.add_css_class("title-1")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)

        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh())
        header.append(refresh)

        self.summary = Gtk.Label()
        self.summary.set_xalign(0)
        self.summary.set_wrap(True)
        self.summary.add_css_class("caption")
        main_box.append(self.summary)

        self.text = Gtk.TextView()
        self.text.set_editable(False)
        self.text.set_monospace(True)
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.add_css_class("monospace")
        main_box.append(self.text)

        self.refresh()

    def refresh(self):
        """Refresh the status page with a new read-only snapshot."""
        try:
            data = snapshot()
            text = self._format_snapshot(data)
            self.summary.set_label("Manual read-only snapshot. No service control, mount changes, or writes.")
        except Exception as exc:
            text = f"Roxy status snapshot failed: {exc}"
            self.summary.set_label("Snapshot failed. No mutation was attempted.")

        buffer = self.text.get_buffer()
        buffer.set_text(text)

    def _format_snapshot(self, data: dict) -> str:
        lines: list[str] = []
        lines.append(f"host: {data.get('host', '')}")
        lines.append(f"generatedAt: {data.get('generatedAt', '')}")
        lines.append(f"providerVersion: {data.get('providerVersion', '')}")
        lines.append("")

        lines.append("proof:")
        for name, item in data.get("proof", {}).items():
            ok = "OK" if item.get("ok") else "WARN"
            label = item.get("url") or item.get("address") or name
            lines.append(f"  {ok:4} {name}: {label}")
        lines.append("")

        lines.append("mounts:")
        for name, item in data.get("mounts", {}).items():
            ok = "OK" if item.get("readonly") else "WARN"
            lines.append(
                f"  {ok:4} {name}: {item.get('source', '')} "
                f"{item.get('fstype', '')} {item.get('options', '')}"
            )
        lines.append("")

        gpu = data.get("gpu", {})
        lines.append("gpu:")
        lines.append(f"  safe lane: {gpu.get('safe_lane_status', '')}")
        lines.append(f"  webgpu max: {gpu.get('webgpu_max_status', '')}")
        verdict = gpu.get("benchmark_verdict") or ""
        if verdict:
            for line in verdict.splitlines():
                lines.append(f"  {line}")
        lines.append("")
        lines.append(gpu.get("vulkan", ""))
        lines.append("")

        lines.append("recovery reports:")
        for path, exists in data.get("recovery_reports", {}).items():
            lines.append(f"  {'OK' if exists else 'WARN'} {path}")
        lines.append("")

        operator_pack = data.get("operator_pack", {})
        lines.append("operator pack:")
        for name, path in operator_pack.get("installed_commands", {}).items():
            lines.append(f"  {'OK' if path else 'WARN'} {name}: {path or 'missing'}")
        for label, item in [
            ("latest visual log", operator_pack.get("latest_visual_log", {})),
            ("latest screenshot", operator_pack.get("latest_screenshot", {})),
            ("latest report", operator_pack.get("latest_report", {})),
            ("latest command center proof", operator_pack.get("latest_command_center_proof", {})),
        ]:
            lines.append(f"  {'OK' if item.get('exists') else 'WARN'} {label}: {item.get('path', '')}")
        lines.append("")

        mos = data.get("mos_control_plane", {})
        lines.append("mos control spine:")
        ingress = mos.get("ingress_health", {})
        authority = mos.get("authority_health", {})
        lines.append(f"  {'OK' if ingress.get('ok') else 'WARN'} ingress health: {ingress.get('url', '')}")
        lines.append(f"  {'OK' if authority.get('ok') else 'WARN'} authority health: {authority.get('url', '')}")
        routes = mos.get("canonical_routes", {})
        lines.append(f"  route canonical: {routes.get('input', '')}")
        lines.append(f"  route alias: {routes.get('alias', '')}")
        lines.append(f"  stream: {routes.get('stream', '')}")
        latest_boot = mos.get("latest_boot_proof", {})
        latest_boot_summary = mos.get("latest_boot_summary", {})
        lines.append(f"  {'OK' if latest_boot.get('exists') else 'WARN'} latest boot proof: {latest_boot.get('path', '')}")
        lines.append(
            "  boot proof summary: "
            f"passed={latest_boot_summary.get('passed')} "
            f"failed={latest_boot_summary.get('failed')} "
            f"tests={latest_boot_summary.get('tests')}"
        )
        inventory = mos.get("inventory", {})
        lines.append(
            f"  {'OK' if inventory.get('exists') else 'WARN'} hardware inventory: "
            f"{inventory.get('path', '')} devices={inventory.get('devices')} updated={inventory.get('lastUpdated')}"
        )
        profiles = mos.get("profiles_source", {})
        lines.append(f"  {'OK' if profiles.get('exists') else 'WARN'} profiles source: {profiles.get('path', '')}")
        listeners = mos.get("listeners", "")
        if listeners:
            lines.append("  listeners:")
            for line in listeners.splitlines():
                lines.append(f"    {line}")
        else:
            lines.append("  listeners: no 49170/49172/49173/9135/19135 matches")
        lines.append("")

        surfaces = data.get("control_surfaces", {})
        lines.append("control surfaces:")
        for device_id, item in surfaces.get("devices", {}).items():
            details = []
            if item.get("usbId"):
                details.append(f"usb={item.get('usbId')}")
            details.append(f"usbPresent={item.get('usbPresent')}")
            details.append(f"byIdPresent={item.get('byIdPresent')}")
            details.append(f"dryRunProven={item.get('dryRunProven')}")
            details.append(f"liveCaptureReady={item.get('liveCaptureReady')}")
            details.append(f"liveCaptureProven={item.get('liveCaptureProven')}")
            details.append(f"routedProven={item.get('routedProven')}")
            if item.get("path"):
                details.append(f"path={item.get('path')}")
            lines.append(f"  {device_id}: {item.get('statusTier')} {' '.join(details)}")
            if item.get("note"):
                lines.append(f"    note: {item.get('note')}")
        python = surfaces.get("python", {})
        lines.append(
            "  python deps: "
            + ", ".join(f"{name}={'present' if present else 'missing'}" for name, present in python.items())
        )
        lines.append(f"  live evdev capture ready: {surfaces.get('evdev_live_capture_ready')}")
        if surfaces.get("note"):
            lines.append(f"  note: {surfaces.get('note')}")
        lines.append("")

        skybeam = data.get("skybeam", {})
        lines.append("skybeam / obs:")
        lines.append(f"  {'OK' if skybeam.get('exists') else 'WARN'} root: {skybeam.get('root', '')}")
        latest_recording = skybeam.get("latest_recording", {})
        latest_meta = skybeam.get("latest_meta", {})
        lines.append(f"  {'OK' if latest_recording.get('exists') else 'WARN'} latest recording: {latest_recording.get('path', '')}")
        lines.append(f"  {'OK' if latest_meta.get('exists') else 'WARN'} latest meta: {latest_meta.get('path', '')}")
        obs_probe = skybeam.get("obs_listener_probe", "")
        lines.append("  obs listener probe:")
        if obs_probe:
            for line in obs_probe.splitlines():
                lines.append(f"    {line}")
        else:
            lines.append("    no :4455/:5960/:5961/:5962 listener observed")
        event_policy = skybeam.get("event_policy", {})
        lines.append(
            "  event policy: "
            f"status={event_policy.get('status')} "
            f"deviceId={event_policy.get('deviceId')} "
            f"sourceType={event_policy.get('sourceType')} "
            f"transport={event_policy.get('transport')} "
            f"route={event_policy.get('route')}"
        )
        if skybeam.get("note"):
            lines.append(f"  note: {skybeam.get('note')}")
        lines.append("")

        lines.append("warnings:")
        for warning in data.get("warnings", []):
            lines.append(f"  - {warning}")

        return "\n".join(lines)
