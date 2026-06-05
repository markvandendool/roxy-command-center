#!/usr/bin/env python3
"""
Mission Dashboard Page — Civilization Command Center.

ROXY-COMMAND-CENTER-MISSION-FIRST-V1

Replaces "Chat First" with "Mission First".
Layout:
  [North: Mission Canvas — cards for active missions]
  [Center: Paned — Agent Civilization | APEX Runtime]
  [South: Compact Command Bar — quick chat + actions]

Design tokens: .moc-card, .moc-panel, .moc-chip-*, .moc-section-label,
  .status-healthy, .status-warn, .status-blocked
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent_discovery_service import AgentDiscoveryService
from services.gpu_monitor import get_gpu_monitor
from services.roxy_status_provider import gpu_status as roxy_gpu_status
from services.mission_truth_provider import MissionTruthProvider
from services.judge_service import get_judge_service
from services.kimi_assignment_service import create_assignment_packet
from services.investigation_service import create_investigation_packet


# =============================================================================
# DATA MODELS
# =============================================================================

class MissionStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warn"
    BLOCKED = "blocked"
    STALLED = "stalled"
    ORPHANED = "orphaned"


@dataclass
class Mission:
    id: str
    name: str
    status: MissionStatus
    health_score: int  # 0-100
    confidence: int  # 0-100
    owner: str
    squad: List[str]
    blockers: List[str]
    receipts: int
    timeline: str
    priority: int  # 0=critical, 1=high, 2=normal
    tags: List[str] = field(default_factory=list)


@dataclass
class ApexLane:
    name: str
    port: int
    model: str
    status: str
    tps: Optional[float]
    vram_used_mb: int
    vram_total_mb: int
    backend: str


# =============================================================================
# MOCK DATA REMOVED — replaced by MissionTruthProvider (canonical SSOT data)
# =============================================================================


# =============================================================================
# UI COMPONENTS
# =============================================================================

class MissionCard(Gtk.Box):
    """A mission card with status border, health bar, metadata, and actions."""

    def __init__(self, mission: Mission):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.mission = mission
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.add_css_class("moc-card")
        self.add_css_class(f"status-{mission.status.value}")

        self._active_judge_job_id: Optional[str] = None
        self._judge_poll_source_id: Optional[int] = None

        self._build_ui()

    def _build_ui(self):
        # Top row: name + status chip
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(top)

        name = Gtk.Label(label=self.mission.name)
        name.add_css_class("moc-row-title")
        name.set_hexpand(True)
        name.set_xalign(0)
        name.set_wrap(True)
        name.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        top.append(name)

        chip = Gtk.Label(label=self.mission.status.value.upper())
        chip.add_css_class("moc-chip")
        if self.mission.status == MissionStatus.HEALTHY:
            chip.add_css_class("moc-chip-success")
        elif self.mission.status == MissionStatus.WARNING:
            chip.add_css_class("moc-chip-warning")
        elif self.mission.status == MissionStatus.BLOCKED:
            chip.add_css_class("moc-chip-danger")
        elif self.mission.status == MissionStatus.STALLED:
            chip.add_css_class("moc-chip-warning")
        elif self.mission.status == MissionStatus.ORPHANED:
            chip.add_css_class("moc-chip-danger")
        top.append(chip)

        # Health + Confidence bars
        self.append(self._make_bar_row("Health", self.mission.health_score, "#35d07f"))
        self.append(self._make_bar_row("Confidence", self.mission.confidence, "#4fd6ff"))

        # Metadata row
        meta = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        meta.set_margin_top(4)
        self.append(meta)

        meta_items = [
            ("👤", self.mission.owner or "unassigned"),
            ("📎", f"{self.mission.receipts} receipts"),
            ("🕐", self.mission.timeline),
        ]
        if self.mission.blockers:
            meta_items.append(("🚧", f"{len(self.mission.blockers)} blocker(s)"))

        for icon, text in meta_items:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            ico = Gtk.Label(label=icon)
            box.append(ico)
            lbl = Gtk.Label(label=text)
            lbl.add_css_class("moc-row-subtitle")
            box.append(lbl)
            meta.append(box)

        # Squad chips
        if self.mission.squad:
            squad_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            squad_box.set_margin_top(4)
            self.append(squad_box)
            for agent in self.mission.squad:
                s = Gtk.Label(label=agent)
                s.add_css_class("moc-chip")
                s.add_css_class("moc-chip-info")
                squad_box.append(s)

        # Action buttons (context-aware)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        actions_box.set_margin_top(6)
        self.append(actions_box)

        # Judge Review — available for all missions
        judge_btn = Gtk.Button(label="⚖️ Judge")
        judge_btn.add_css_class("pill")
        judge_btn.add_css_class("caption")
        judge_btn.set_tooltip_text("Send mission to Judge for adversarial review")
        judge_btn.connect("clicked", self._on_judge_clicked)
        actions_box.append(judge_btn)

        # Kimi Assign — available for campaign missions
        is_campaign = self.mission.id.startswith("campaign-")
        if is_campaign:
            kimi_btn = Gtk.Button(label="🤖 Kimi")
            kimi_btn.add_css_class("pill")
            kimi_btn.add_css_class("caption")
            kimi_btn.set_tooltip_text("Assign to Kimi long-runner swarm")
            kimi_btn.connect("clicked", self._on_kimi_clicked)
            actions_box.append(kimi_btn)

        # Investigate — for blockers and subsystems
        is_blocker = self.mission.id.startswith("blocker-") or self.mission.id.startswith("subsys-")
        if is_blocker:
            invest_btn = Gtk.Button(label="🔍 Investigate")
            invest_btn.add_css_class("pill")
            invest_btn.add_css_class("caption")
            invest_btn.set_tooltip_text("Open investigation for this blocker")
            invest_btn.connect("clicked", self._on_investigate_clicked)
            actions_box.append(invest_btn)

        # Judge Results — show completed jobs for this mission
        self._build_judge_results()

        # Truth grade + data source footer
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(4)
        self.append(footer)

        grade_colors = {
            "live_probe": ("moc-chip-success", "🔴 live"),
            "receipt_derived": ("moc-chip-warning", "📜 receipt"),
            "governed_packet": ("moc-chip-info", "📋 governed"),
            "stale_log": ("moc-chip-danger", "⚪ stale"),
            "retired": ("moc-chip-danger", "🪦 retired"),
        }
        grade_cls, grade_label = grade_colors.get(self.mission.truth_grade, ("moc-chip-warning", f"❓ {self.mission.truth_grade}"))
        grade_chip = Gtk.Label(label=grade_label)
        grade_chip.add_css_class("moc-chip")
        grade_chip.add_css_class(grade_cls)
        grade_chip.set_tooltip_text(f"Truth grade: {self.mission.truth_grade}")
        footer.append(grade_chip)

        src_lbl = Gtk.Label(label=f"📡 {self.mission.data_source}")
        src_lbl.add_css_class("moc-row-subtitle")
        src_lbl.set_xalign(0)
        footer.append(src_lbl)

    def _on_judge_clicked(self, button):
        """Send mission to Judge for adversarial review — creates real job."""
        prompt = (
            f"Mission: {self.mission.name}\n"
            f"Status: {self.mission.status.value}\n"
            f"Owner: {self.mission.owner}\n"
            f"Blockers: {', '.join(self.mission.blockers) or 'None'}\n"
            f"Squad: {', '.join(self.mission.squad) or 'None'}\n"
            f"Source: {self.mission.data_source}\n\n"
            "Please perform an adversarial review. Identify errors, assumptions, gaps, or quality issues."
        )
        job = get_judge_service().submit_job(
            prompt=prompt,
            context=self.mission.name,
            source_mission_id=self.mission.id,
            on_complete=self._on_judge_complete,
        )
        self._active_judge_job_id = job.job_id
        # Update button to show queued state
        button.set_label("⏳ Judge queued")
        button.set_sensitive(False)
        button.set_tooltip_text(f"Job {job.job_id} — polling for completion")
        # Start fallback poller every 3s
        self._judge_poll_source_id = GLib.timeout_add_seconds(3, self._poll_judge_status)

    def _on_judge_complete(self, job):
        """Callback when Judge job finishes (called from background thread)."""
        GLib.idle_add(self._update_judge_ui, job)

    def _update_judge_ui(self, job):
        """Update UI from main thread when Judge job completes."""
        if self._judge_poll_source_id:
            GLib.source_remove(self._judge_poll_source_id)
            self._judge_poll_source_id = None
        self._active_judge_job_id = None
        self._show_judge_result(job)
        return False  # idle callback single shot

    def _poll_judge_status(self):
        """Fallback poller — checks job file on disk."""
        if not self._active_judge_job_id:
            return False  # Stop polling
        job = get_judge_service().get_job(self._active_judge_job_id)
        if job and job.status in ("completed", "failed", "timeout"):
            self._on_judge_complete(job)
            return False  # Stop polling — callback handles UI update
        return True  # Continue polling

    def _show_judge_result(self, job):
        """Display Judge result inline in the mission card."""
        # Remove any existing result box
        if hasattr(self, '_result_box') and self._result_box.get_parent() == self:
            self.remove(self._result_box)

        self._result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._result_box.set_margin_top(6)

        status_icon = "✅" if job.status == "completed" else "❌"
        header = Gtk.Label(label=f"{status_icon} Judge {job.status}")
        header.add_css_class("caption")
        header.add_css_class("accent")
        header.set_xalign(0)
        self._result_box.append(header)

        if job.result:
            preview = job.result[:200] + "…" if len(job.result) > 200 else job.result
            preview = preview.replace("\n", " ")
            lbl = Gtk.Label(label=preview)
            lbl.add_css_class("caption")
            lbl.set_xalign(0)
            lbl.set_wrap(True)
            lbl.set_selectable(True)
            self._result_box.append(lbl)

        if job.error:
            err = Gtk.Label(label=f"Error: {job.error}")
            err.add_css_class("caption")
            err.add_css_class("error")
            err.set_xalign(0)
            self._result_box.append(err)

        self.append(self._result_box)

    def _on_kimi_clicked(self, button):
        """Assign mission to Kimi — creates real assignment packet."""
        result = create_assignment_packet(
            mission_id=self.mission.id,
            mission_title=self.mission.name,
            brief=(
                f"Mission: {self.mission.name}\n"
                f"Status: {self.mission.status.value}\n"
                f"Blockers: {', '.join(self.mission.blockers) or 'None'}\n"
                f"Source: {self.mission.data_source}"
            ),
        )
        packet = result["packet"]
        button.set_label(f"🤖 Kimi → {packet['targetSurface']}")
        button.set_sensitive(False)
        button.set_tooltip_text(f"Packet {packet['packetId']} queued for {packet['targetSurface']}")

    def _on_investigate_clicked(self, button):
        """Create read-only investigation packet."""
        result = create_investigation_packet(
            mission_id=self.mission.id,
            mission_title=self.mission.name,
            question=f"Investigate mission '{self.mission.name}': what is the root cause and recommended fix?",
            source_artifacts=[self.mission.data_source],
        )
        packet = result["packet"]
        button.set_label("📋 Investigate queued")
        button.set_sensitive(False)
        button.set_tooltip_text(f"Packet {packet['packetId']} queued for read-only investigation")

    def _build_judge_results(self):
        """Show completed Judge review jobs for this mission."""
        try:
            from services.judge_service import get_judge_service
            jobs = get_judge_service().list_jobs(limit=50)
            mission_jobs = [
                j for j in jobs
                if j.get("sourceMissionId") == self.mission.id and j.get("status") == "completed"
            ]
            if not mission_jobs:
                return

            results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            results_box.set_margin_top(6)
            self.append(results_box)

            header = Gtk.Label(label="⚖️ Judge Results")
            header.add_css_class("caption")
            header.add_css_class("accent")
            header.set_xalign(0)
            results_box.append(header)

            for job in mission_jobs[:2]:  # Show max 2 results
                result_text = job.get("result", "")
                preview = result_text[:120] + "…" if len(result_text) > 120 else result_text
                preview = preview.replace("\n", " ")

                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row.set_margin_start(4)
                results_box.append(row)

                lbl = Gtk.Label(label=f"• {preview}")
                lbl.add_css_class("caption")
                lbl.set_xalign(0)
                lbl.set_wrap(True)
                lbl.set_selectable(True)
                row.append(lbl)

        except Exception as exc:
            print(f"[MissionCard] Judge results error: {exc}")

    def _make_bar_row(self, label: str, value: int, color: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(2)

        lbl = Gtk.Label(label=f"{label}")
        lbl.add_css_class("moc-row-subtitle")
        lbl.set_size_request(70, -1)
        lbl.set_xalign(0)
        row.append(lbl)

        # Progress bar
        bar = Gtk.ProgressBar()
        bar.set_fraction(value / 100.0)
        bar.set_hexpand(True)
        bar.set_size_request(-1, 6)
        bar.add_css_class("mission-health-bar")
        row.append(bar)

        val = Gtk.Label(label=f"{value}%")
        val.add_css_class("moc-row-subtitle")
        val.set_size_request(36, -1)
        val.set_xalign(1)
        row.append(val)

        return row


class AgentCivilizationPanel(Gtk.Box):
    """Compact agent roster with health and status."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_bottom(12)
        self.add_css_class("moc-panel")

        self._discovery = AgentDiscoveryService()
        self._rows: Dict[str, Gtk.Box] = {}

        self._build_ui()

    def _build_ui(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        title = Gtk.Label(label="Agent Civilization")
        title.add_css_class("moc-section-label")
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)

        self._count_label = Gtk.Label(label="—")
        self._count_label.add_css_class("moc-row-subtitle")
        header.append(self._count_label)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        self.append(sep)

        self._list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self._list_box)

        self._refresh()

    def _refresh(self):
        # Clear existing
        while self._list_box.get_first_child():
            self._list_box.remove(self._list_box.get_first_child())
        self._rows.clear()

        try:
            packets = self._discovery.get_agent_packets()
        except Exception:
            packets = []

        if not packets:
            empty = Gtk.Label(label="No agents discovered")
            empty.add_css_class("dim-label")
            empty.set_margin_top(12)
            self._list_box.append(empty)
            self._count_label.set_label("0")
            return

        active = sum(1 for p in packets if p.status == "active")
        self._count_label.set_label(f"{active}/{len(packets)} active")

        for pkt in packets[:12]:  # cap at 12 for compactness
            row = self._build_agent_row(pkt)
            self._list_box.append(row)
            self._rows[pkt.agent_id] = row

    def _build_agent_row(self, pkt) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-object-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        # Status dot
        if pkt.status == "active":
            row.add_css_class("status-healthy")
        elif pkt.status in ("stale", "blocked"):
            row.add_css_class("status-blocked")
        else:
            row.add_css_class("status-warn")

        # Name
        name = Gtk.Label(label=pkt.agent_id[:24])
        name.add_css_class("moc-row-title")
        name.set_size_request(140, -1)
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)

        # Lane chip
        lane = Gtk.Label(label=pkt.lane or "unknown")
        lane.add_css_class("moc-chip")
        lane.add_css_class("moc-chip-info")
        row.append(lane)

        # Health bar (if available)
        if hasattr(pkt, 'health_score') and pkt.health_score > 0:
            bar = Gtk.ProgressBar()
            bar.set_fraction(pkt.health_score / 100.0)
            bar.set_size_request(60, 4)
            bar.set_hexpand(True)
            row.append(bar)
        else:
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            row.append(spacer)

        # Status chip
        st = Gtk.Label(label=pkt.status)
        st.add_css_class("moc-chip")
        if pkt.status == "active":
            st.add_css_class("moc-chip-success")
        elif pkt.status in ("stale", "blocked"):
            st.add_css_class("moc-chip-danger")
        else:
            st.add_css_class("moc-chip-warning")
        row.append(st)

        return row

    def update(self, data: dict):
        self._refresh()


class ApexRuntimePanel(Gtk.Box):
    """APEX inference lane status panel."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_margin_top(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_bottom(12)
        self.add_css_class("moc-panel")

        self._gpu_monitor = get_gpu_monitor()
        self._lane_rows: Dict[str, Gtk.Box] = {}

        self._build_ui()

    def _build_ui(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        title = Gtk.Label(label="APEX Runtime")
        title.add_css_class("moc-section-label")
        title.set_hexpand(True)
        title.set_xalign(0)
        header.append(title)

        self._overall_label = Gtk.Label(label="—")
        self._overall_label.add_css_class("moc-chip")
        self._overall_label.add_css_class("moc-chip-success")
        header.append(self._overall_label)

        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(4)
        sep.set_margin_bottom(4)
        self.append(sep)

        self._lanes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self._lanes_box)

        self._gpu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._gpu_box.set_margin_top(8)
        self.append(self._gpu_box)

        self._refresh()

    def _refresh(self):
        # Clear lanes
        while self._lanes_box.get_first_child():
            self._lanes_box.remove(self._lanes_box.get_first_child())
        self._lane_rows.clear()

        lanes = MissionTruthProvider.get_apex_lanes()
        # Consider "healthy" only if live_probe or cloud_api
        live_healthy = all(
            l.status == "healthy" and l.truth_grade in ("live_probe", "cloud_api")
            for l in lanes if l.status != "retired"
        )
        has_retired = any(l.status == "retired" for l in lanes)
        self._overall_label.set_label("GREEN" if live_healthy else "DEGRADED")
        if live_healthy:
            self._overall_label.remove_css_class("moc-chip-danger")
            self._overall_label.add_css_class("moc-chip-success")
        else:
            self._overall_label.remove_css_class("moc-chip-success")
            self._overall_label.add_css_class("moc-chip-danger")

        for lane in lanes:
            row = self._build_lane_row(lane)
            self._lanes_box.append(row)
            self._lane_rows[lane.name] = row

        # GPU section
        while self._gpu_box.get_first_child():
            self._gpu_box.remove(self._gpu_box.get_first_child())

        try:
            gpus = self._gpu_monitor.get_gpus()
        except Exception:
            gpus = {}

        if gpus:
            gpu_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            self._gpu_box.append(gpu_sep)
            gpu_title = Gtk.Label(label="GPU Sensors")
            gpu_title.add_css_class("moc-section-label")
            gpu_title.set_margin_top(4)
            gpu_title.set_xalign(0)
            self._gpu_box.append(gpu_title)

            for idx, gpu in gpus.items():
                g_row = self._build_gpu_row(gpu)
                self._gpu_box.append(g_row)

    def _build_lane_row(self, lane: ApexLane) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("moc-procedure-row")
        row.set_margin_top(2)
        row.set_margin_bottom(2)

        # Status styling based on truth grade, not just status string
        if lane.truth_grade == "live_probe" and lane.status == "healthy":
            row.add_css_class("status-healthy")
        elif lane.truth_grade == "cloud_api":
            row.add_css_class("status-healthy")
        elif lane.truth_grade == "retired":
            row.add_css_class("status-warn")
        elif lane.truth_grade == "stale_log":
            row.add_css_class("status-warn")
        else:
            row.add_css_class("status-blocked")

        # Name + model
        name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_box.set_size_request(180, -1)

        name = Gtk.Label(label=f"{lane.name}")
        name.add_css_class("moc-row-title")
        name.set_xalign(0)
        name_box.append(name)

        model = Gtk.Label(label=f"{lane.model}")
        model.add_css_class("moc-row-subtitle")
        model.set_xalign(0)
        model.set_ellipsize(Pango.EllipsizeMode.END)
        name_box.append(model)

        row.append(name_box)

        # Truth grade chip
        grade_labels = {
            "live_probe": "🔴 live",
            "cloud_api": "☁️ cloud",
            "stale_log": "⚪ stale",
            "retired": "🪦 retired",
        }
        grade_text = grade_labels.get(lane.truth_grade, f"❓ {lane.truth_grade}")
        grade_chip = Gtk.Label(label=grade_text)
        grade_chip.add_css_class("moc-chip")
        if lane.truth_grade == "live_probe":
            grade_chip.add_css_class("moc-chip-success")
        elif lane.truth_grade == "cloud_api":
            grade_chip.add_css_class("moc-chip-info")
        elif lane.truth_grade in ("stale_log", "retired"):
            grade_chip.add_css_class("moc-chip-warning")
        else:
            grade_chip.add_css_class("moc-chip-danger")
        row.append(grade_chip)

        # Port
        port = Gtk.Label(label=f":{lane.port}")
        port.add_css_class("moc-chip")
        port.add_css_class("moc-chip-info")
        row.append(port)

        # TPS
        if lane.tps is not None:
            tps = Gtk.Label(label=f"{lane.tps:.1f} t/s")
            tps.add_css_class("moc-row-value")
            tps.set_size_request(80, -1)
            tps.set_xalign(1)
            row.append(tps)
        else:
            spacer = Gtk.Box()
            spacer.set_size_request(80, -1)
            row.append(spacer)

        # VRAM bar (if applicable)
        if lane.vram_total_mb > 0:
            vram_frac = lane.vram_used_mb / lane.vram_total_mb
            vram_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vram_box.set_size_request(100, -1)
            vram_box.set_hexpand(True)

            vram_bar = Gtk.ProgressBar()
            vram_bar.set_fraction(vram_frac)
            vram_bar.set_size_request(-1, 4)
            vram_box.append(vram_bar)

            vram_lbl = Gtk.Label(
                label=f"{lane.vram_used_mb}/{lane.vram_total_mb} MiB"
            )
            vram_lbl.add_css_class("moc-row-subtitle")
            vram_lbl.set_xalign(1)
            vram_box.append(vram_lbl)

            row.append(vram_box)
        else:
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            row.append(spacer)

        return row

    def _build_gpu_row(self, gpu) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_margin_top(4)
        row.set_margin_bottom(4)

        name = Gtk.Label(label=gpu.name[:28])
        name.add_css_class("moc-row-title")
        name.set_size_request(160, -1)
        name.set_xalign(0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        row.append(name)

        temp = Gtk.Label(label=f"{gpu.temp:.0f}°C")
        temp.add_css_class("moc-row-subtitle")
        temp.set_size_request(50, -1)
        row.append(temp)

        util = Gtk.Label(label=f"{gpu.util_percent:.0f}%")
        util.add_css_class("moc-row-value")
        util.set_size_request(50, -1)
        util.set_xalign(1)
        row.append(util)

        pwr = Gtk.Label(label=f"{gpu.power_w:.0f}W")
        pwr.add_css_class("moc-row-subtitle")
        pwr.set_size_request(50, -1)
        pwr.set_xalign(1)
        row.append(pwr)

        return row

    def update(self, data: dict):
        self._refresh()


class CompactCommandBar(Gtk.Box):
    """Bottom command bar — quick chat input + action buttons."""

    def __init__(self, on_chat: Optional[callable] = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_bottom(8)
        self.add_css_class("moc-rail")

        self.on_chat = on_chat
        self._build_ui()

    def _build_ui(self):
        # Quick action buttons
        actions = [
            ("🎯", "Missions", None),
            ("🧠", "Brain", None),
            ("⚡", "APEX", None),
            ("👥", "Agents", None),
        ]
        for icon, label, cb in actions:
            btn = Gtk.Button(label=f"{icon} {label}")
            btn.add_css_class("flat")
            btn.add_css_class("moc-chip")
            btn.add_css_class("moc-chip-info")
            self.append(btn)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep.set_margin_start(8)
        sep.set_margin_end(8)
        self.append(sep)

        # Chat entry
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ask Roxy anything...")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._on_activate)
        self.append(self.entry)

        send = Gtk.Button(label="Send")
        send.add_css_class("suggested-action")
        send.connect("clicked", self._on_send)
        self.append(send)

    def _on_activate(self, entry):
        self._on_send(None)

    def _on_send(self, _btn):
        text = self.entry.get_text().strip()
        if text and self.on_chat:
            self.on_chat(text)
        self.entry.set_text("")


# =============================================================================
# MAIN PAGE
# =============================================================================

class MissionDashboardPage(Gtk.Box):
    """
    Mission-First Command Center.

    Layout (vertical):
      1. Mission Canvas (scrollable flow box)
      2. Paned: Agent Civilization | APEX Runtime
      3. Compact Command Bar
    """

    def __init__(self, on_navigate: Optional[callable] = None, on_chat: Optional[callable] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_navigate = on_navigate
        self.on_chat = on_chat
        self.add_css_class("mission-dashboard-page")

        self._build_ui()

    def _build_ui(self):
        # === SCROLLABLE CONTENT ===
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_margin_bottom(12)
        scroll.set_child(content)

        # --- Mission Canvas ---
        canvas_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(canvas_header)

        canvas_title = Gtk.Label(label="Active Missions")
        canvas_title.add_css_class("moc-section-label")
        canvas_title.set_hexpand(True)
        canvas_title.set_xalign(0)
        canvas_header.append(canvas_title)

        self._mission_count = Gtk.Label(label="—")
        self._mission_count.add_css_class("moc-row-subtitle")
        canvas_header.append(self._mission_count)

        self._mission_flow = Gtk.FlowBox()
        self._mission_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._mission_flow.set_max_children_per_line(3)
        self._mission_flow.set_min_children_per_line(1)
        self._mission_flow.set_homogeneous(True)
        self._mission_flow.set_column_spacing(12)
        self._mission_flow.set_row_spacing(12)
        content.append(self._mission_flow)

        self._load_missions()
        self._start_refresh_timers()

        # --- Middle Paned: Agents | APEX ---
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_wide_handle(True)
        paned.set_vexpand(True)
        paned.set_size_request(-1, 280)
        content.append(paned)

        self._agent_panel = AgentCivilizationPanel()
        self._agent_panel.set_size_request(360, -1)
        paned.set_start_child(self._agent_panel)

        self._apex_panel = ApexRuntimePanel()
        self._apex_panel.set_size_request(360, -1)
        paned.set_end_child(self._apex_panel)

        # === COMPACT COMMAND BAR ===
        self._cmd_bar = CompactCommandBar(on_chat=self.on_chat)
        self.append(self._cmd_bar)

    def _load_missions(self):
        missions = MissionTruthProvider.get_missions()
        self._mission_count.set_label(f"{len(missions)} missions")

        for mission in missions:
            card = MissionCard(mission)
            self._mission_flow.append(card)

    def _start_refresh_timers(self):
        """Start auto-refresh and judge poller timers (called once)."""
        self._auto_refresh_id = GLib.timeout_add_seconds(10, self._auto_refresh)
        self._judge_poll_id = GLib.timeout_add_seconds(5, self._poll_judge_jobs)

    def _auto_refresh(self):
        """Reload missions and lanes from canonical sources."""
        # Clear missions
        while self._mission_flow.get_first_child():
            self._mission_flow.remove(self._mission_flow.get_first_child())
        self._load_missions()
        self._apex_panel._refresh()
        return True  # Continue polling

    def _poll_judge_jobs(self):
        """Poll for completed Judge jobs — cards handle their own updates via callbacks."""
        # MissionCard instances use on_complete callback + fallback poller.
        # This global poller is a safety net for jobs created outside cards.
        return True  # Continue polling

    def update(self, data: dict):
        """Update from daemon data."""
        self._agent_panel.update(data)
        self._apex_panel.update(data)
