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
# MOCK DATA (until real mission API exists)
# =============================================================================

class MissionDataStore:
    """Placeholder mission data."""

    @classmethod
    def get_missions(cls) -> List[Mission]:
        return [
            Mission(
                id="m1", name="Theater Runtime Stability",
                status=MissionStatus.HEALTHY, health_score=92, confidence=88,
                owner="claude", squad=["claude", "kimi"],
                blockers=[], receipts=4,
                timeline="2d remaining", priority=0,
                tags=["runtime", "webgpu"]
            ),
            Mission(
                id="m2", name="Brain Quality Guard",
                status=MissionStatus.WARNING, health_score=67, confidence=72,
                owner="roxy", squad=["roxy-judge"],
                blockers=["Judge 235B fetch timeout"], receipts=2,
                timeline="ongoing", priority=0,
                tags=["brain", "judge"]
            ),
            Mission(
                id="m3", name="Kimi Long Runner Integration",
                status=MissionStatus.HEALTHY, health_score=85, confidence=90,
                owner="codex", squad=["codex", "kimi"],
                blockers=[], receipts=3,
                timeline="1d remaining", priority=1,
                tags=["infrastructure", "kimi"]
            ),
            Mission(
                id="m4", name="Agent Reputation Convergence",
                status=MissionStatus.STALLED, health_score=45, confidence=40,
                owner="unassigned", squad=[],
                blockers=["No canonical reputation API"], receipts=1,
                timeline="stalled 3d", priority=1,
                tags=["agents", "reputation"]
            ),
            Mission(
                id="m5", name="GPU Canon — Ada Affinity",
                status=MissionStatus.HEALTHY, health_score=95, confidence=95,
                owner="roxy", squad=["roxy-apex"],
                blockers=[], receipts=6,
                timeline="stable", priority=2,
                tags=["apex", "gpu"]
            ),
            Mission(
                id="m6", name="UI Authority Violation Cleanup",
                status=MissionStatus.HEALTHY, health_score=100, confidence=100,
                owner="kimi", squad=["kimi"],
                blockers=[], receipts=2,
                timeline="completed", priority=2,
                tags=["governance", "ui"]
            ),
        ]

    @classmethod
    def get_apex_lanes(cls) -> List[ApexLane]:
        return [
            ApexLane("ada-coder-frontier", 8085, "Qwen3.6-27B Q4_K_M MTP",
                     "healthy", 36.2, 17913, 20475, "cuda"),
            ApexLane("llama-cpp-cpu", 8084, "Qwen3-235B Q3_K_L",
                     "healthy", 3.5, 0, 0, "cpu"),
            ApexLane("llama-cpp-vulkan-6900xt", 8083, "Qwen2.5-7B Q4_K_M",
                     "healthy", 84.0, 2150, 16384, "vulkan"),
            ApexLane("llama-cpp-vulkan-w5700x", 8082, "Qwen2.5-7B Q4_K_M",
                     "healthy", 83.0, 4367, 16368, "vulkan"),
            ApexLane("ollama", 11434, "qwen2.5-coder:14b",
                     "healthy", None, 0, 0, "ollama"),
            ApexLane("litellm-gateway", 4000, "10 models",
                     "healthy", None, 0, 0, "gateway"),
        ]


# =============================================================================
# UI COMPONENTS
# =============================================================================

class MissionCard(Gtk.Box):
    """A mission card with status border, health bar, and metadata."""

    def __init__(self, mission: Mission):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.mission = mission
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.add_css_class("moc-card")
        self.add_css_class(f"status-{mission.status.value}")

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

        lanes = MissionDataStore.get_apex_lanes()
        all_healthy = all(l.status == "healthy" for l in lanes)
        self._overall_label.set_label("GREEN" if all_healthy else "DEGRADED")
        if all_healthy:
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

        if lane.status == "healthy":
            row.add_css_class("status-healthy")
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
        missions = MissionDataStore.get_missions()
        self._mission_count.set_label(f"{len(missions)} missions")

        for mission in missions:
            card = MissionCard(mission)
            self._mission_flow.append(card)

    def update(self, data: dict):
        """Update from daemon data."""
        self._agent_panel.update(data)
        self._apex_panel.update(data)
