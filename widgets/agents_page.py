#!/usr/bin/env python3
"""
Agents Page — Agent leak visibility, MCP counts, tmux sessions.
Diagnose button only. No blind kill.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any, List


class AgentRow(Gtk.Box):
    """Row for a single agent process."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_top(2)
        self.set_margin_bottom(2)
        self.add_css_class("process-row")

        self.pid_label = Gtk.Label(label="")
        self.pid_label.set_size_request(60, -1)
        self.pid_label.add_css_class("monospace-small")
        self.append(self.pid_label)

        self.provider_label = Gtk.Label(label="")
        self.provider_label.set_size_request(60, -1)
        self.provider_label.add_css_class("monospace-small")
        self.append(self.provider_label)

        self.class_label = Gtk.Label(label="")
        self.class_label.set_size_request(80, -1)
        self.append(self.class_label)

        self.cpu_label = Gtk.Label(label="")
        self.cpu_label.set_size_request(60, -1)
        self.cpu_label.add_css_class("monospace-small")
        self.append(self.cpu_label)

        self.rss_label = Gtk.Label(label="")
        self.rss_label.set_size_request(70, -1)
        self.rss_label.add_css_class("monospace-small")
        self.append(self.rss_label)

        self.time_label = Gtk.Label(label="")
        self.time_label.add_css_class("monospace-small")
        self.time_label.set_hexpand(True)
        self.time_label.set_xalign(0)
        self.append(self.time_label)

    def set(self, pid: int, provider: str, classification: str, pcpu: float, rss: int, elapsed_sec: int):
        self.pid_label.set_label(str(pid))
        self.provider_label.set_label(provider[:5])
        self.class_label.set_label(classification)
        self.cpu_label.set_label(f"{pcpu:.1f}%")
        self.rss_label.set_label(f"{rss}M")
        hours = elapsed_sec // 3600
        mins = (elapsed_sec % 3600) // 60
        self.time_label.set_label(f"{hours}h {mins}m")

        self.remove_css_class("agent-active")
        self.remove_css_class("agent-idle")
        self.remove_css_class("agent-abandoned")
        if classification in ("active", "idle", "abandoned"):
            self.add_css_class(f"agent-{classification}")


class AgentsPage(Gtk.ScrolledWindow):
    """Agent observability dashboard."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._agent_rows: List[AgentRow] = []
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Agents")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # Summary cards
        summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        summary_box.set_homogeneous(True)
        main_box.append(summary_box)

        self.total_card = self._make_summary_card("Total Agents")
        summary_box.append(self.total_card)

        self.active_card = self._make_summary_card("Active")
        summary_box.append(self.active_card)

        self.abandoned_card = self._make_summary_card("Abandoned")
        summary_box.append(self.abandoned_card)

        self.mcp_card = self._make_summary_card("MCP Total")
        summary_box.append(self.mcp_card)

        # Tmux summary
        tmux_title = Gtk.Label(label="Tmux Sessions")
        tmux_title.add_css_class("title-3")
        tmux_title.set_xalign(0)
        tmux_title.set_margin_top(16)
        main_box.append(tmux_title)

        self.tmux_label = Gtk.Label(label="—")
        self.tmux_label.add_css_class("monospace-small")
        self.tmux_label.set_xalign(0)
        main_box.append(self.tmux_label)

        # MCP breakdown
        mcp_title = Gtk.Label(label="MCP Breakdown")
        mcp_title.add_css_class("title-3")
        mcp_title.set_xalign(0)
        mcp_title.set_margin_top(16)
        main_box.append(mcp_title)

        self.mcp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.mcp_box.set_margin_top(8)
        main_box.append(self.mcp_box)

        # Agent table header
        agents_title = Gtk.Label(label="Agent Processes")
        agents_title.add_css_class("title-3")
        agents_title.set_xalign(0)
        agents_title.set_margin_top(16)
        main_box.append(agents_title)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.add_css_class("process-header")
        for col, width in [("PID", 60), ("Prov", 60), ("Class", 80), ("CPU%", 60), ("RSS", 70), ("Time", -1)]:
            lbl = Gtk.Label(label=col)
            lbl.add_css_class("monospace-small")
            lbl.set_xalign(0)
            if width > 0:
                lbl.set_size_request(width, -1)
            else:
                lbl.set_hexpand(True)
            header.append(lbl)
        main_box.append(header)

        self.agents_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        main_box.append(self.agents_box)

        # Diagnose button
        self.diagnose_btn = Gtk.Button(label="Diagnose")
        self.diagnose_btn.add_css_class("suggested-action")
        self.diagnose_btn.set_margin_top(16)
        self.diagnose_btn.connect("clicked", self._on_diagnose)
        main_box.append(self.diagnose_btn)

        self.diagnose_output = Gtk.Label(label="")
        self.diagnose_output.add_css_class("monospace-small")
        self.diagnose_output.set_xalign(0)
        self.diagnose_output.set_wrap(True)
        main_box.append(self.diagnose_output)

    def _make_summary_card(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("overview-card")
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        t = Gtk.Label(label=title)
        t.add_css_class("overview-title")
        t.set_xalign(0)
        box.append(t)

        v = Gtk.Label(label="0")
        v.add_css_class("overview-value")
        v.set_xalign(0)
        box.append(v)

        return box

    def _on_diagnose(self, btn):
        import subprocess
        try:
            result = subprocess.run(
                ["node", "/mnt/work/ssot/mindsong-juke-hub/scripts/roxy/roxy-agent-window-doctor.mjs"],
                capture_output=True, text=True, timeout=10
            )
            text = result.stdout or result.stderr or "No output"
            self.diagnose_output.set_label(text[:500])
        except Exception as e:
            self.diagnose_output.set_label(f"Diagnose failed: {e}")

    def update(self, data: dict):
        perf = data.get("performance", {})
        agents = perf.get("agents", {})
        mcp = perf.get("mcp", {})
        tmux = perf.get("tmux", {})

        total = agents.get("total", 0)
        active = agents.get("active", 0)
        abandoned = agents.get("abandoned", 0)
        mcp_total = mcp.get("total", 0)

        # Update summary cards
        def set_card(box, value, status="healthy"):
            child = box.get_first_child()
            if child:
                child = child.get_next_sibling()
                if child:
                    child.set_label(str(value))
            box.remove_css_class("status-healthy")
            box.remove_css_class("status-warn")
            box.remove_css_class("status-blocked")
            if status in ("healthy", "warn", "blocked"):
                box.add_css_class(f"status-{status}")

        set_card(self.total_card, total)
        set_card(self.active_card, active)
        set_card(self.abandoned_card, abandoned, "blocked" if abandoned > 5 else "warn" if abandoned > 0 else "healthy")
        set_card(self.mcp_card, mcp_total, "blocked" if mcp_total > 80 else "warn" if mcp_total > 50 else "healthy")

        # Tmux status
        if tmux.get("error"):
            self.tmux_label.set_label(f"tmux: {tmux['error'][:120]}")
            self.tmux_label.add_css_class("status-blocked-text")
        else:
            tmux_total = tmux.get("total", 0)
            stale = tmux.get("staleCount", 0)
            emergency = tmux.get("emergencyCount", 0)
            self.tmux_label.set_label(
                f"{tmux_total} sessions · {stale} stale · {emergency} emergency"
            )
            self.tmux_label.remove_css_class("status-blocked-text")
            if stale > 0 or emergency > 0:
                self.tmux_label.add_css_class("status-warn-text")
            else:
                self.tmux_label.remove_css_class("status-warn-text")

        # MCP breakdown
        while self.mcp_box.get_first_child():
            self.mcp_box.remove(self.mcp_box.get_first_child())

        counts = mcp.get("counts", {})
        for mcp_type, count in sorted(counts.items(), key=lambda x: -x[1]):
            badge = Gtk.Label(label=f"{mcp_type}: {count}")
            badge.add_css_class("source-badge")
            badge.add_css_class("source-daemon")
            badge.set_margin_end(8)
            self.mcp_box.append(badge)

        # Agent rows
        agent_list = agents.get("list", [])
        if len(agent_list) != len(self._agent_rows):
            while self.agents_box.get_first_child():
                self.agents_box.remove(self.agents_box.get_first_child())
            self._agent_rows = []
            for agent in agent_list:
                row = AgentRow()
                self._agent_rows.append(row)
                self.agents_box.append(row)

        for i, agent in enumerate(agent_list):
            if i < len(self._agent_rows):
                self._agent_rows[i].set(
                    agent.get("pid", 0),
                    agent.get("provider", "?"),
                    agent.get("classification", "?"),
                    agent.get("pcpu", 0),
                    agent.get("rssMiB", 0),
                    agent.get("elapsedSec", 0),
                )
