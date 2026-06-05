#!/usr/bin/env python3
"""
Overview Page — LifePanel Command Center.
One glance tells Mark whether the estate is alive, useful, and safe.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any

from widgets.graph_widget import SparklineWidget
from services.telemetry_collector import get_collector


class LifeCard(Gtk.Box):
    """Compact live summary card for the LifePanel canvas."""

    def __init__(self, title: str, icon_name: str = "", on_click: Optional[callable] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("overview-card")
        self.add_css_class("moc-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.on_click = on_click

        if on_click:
            click = Gtk.GestureClick()
            click.connect("pressed", lambda g, n, x, y: on_click())
            self.add_controller(click)
            self.set_cursor_from_name("pointer")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(18)
            header.append(icon)

        self.title_label = Gtk.Label(label=title)
        self.title_label.add_css_class("overview-title")
        self.title_label.set_xalign(0)
        self.title_label.set_hexpand(True)
        header.append(self.title_label)

        self.value_label = Gtk.Label(label="--")
        self.value_label.add_css_class("overview-value")
        self.value_label.set_xalign(0)
        self.append(self.value_label)

        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.add_css_class("overview-subtitle")
        self.subtitle_label.set_xalign(0)
        self.subtitle_label.set_wrap(True)
        self.append(self.subtitle_label)

        self.sparkline = SparklineWidget(color=(0.13, 0.77, 0.37))
        self.sparkline.set_margin_top(4)
        self.append(self.sparkline)

    def set(self, value: str, subtitle: str = "", status: str = "healthy", history: list = None):
        self.value_label.set_label(value)
        self.subtitle_label.set_label(subtitle)
        self.remove_css_class("status-healthy")
        self.remove_css_class("status-warn")
        self.remove_css_class("status-blocked")
        if status in ("healthy", "warn", "blocked"):
            self.add_css_class(f"status-{status}")
        if history is not None and len(history) >= 2:
            self.sparkline.set_history(history)
        else:
            self.sparkline.set_history([])


class OverviewPage(Gtk.ScrolledWindow):
    """Native LifePanel home: object rail, mission canvas, procedure inspector."""

    def __init__(self, on_navigate: Optional[callable] = None):
        super().__init__()
        self.on_navigate = on_navigate
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cards: Dict[str, LifeCard] = {}
        self._fact_rows: Dict[str, Dict[str, Gtk.Widget]] = {}
        self._procedure_rows: Dict[str, Dict[str, Gtk.Widget]] = {}
        self._build_ui()

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.add_css_class("moc-surface")
        outer.set_margin_top(18)
        outer.set_margin_bottom(18)
        outer.set_margin_start(18)
        outer.set_margin_end(18)
        self.set_child(outer)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        outer.append(title_row)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        title_row.append(title_box)

        title = Gtk.Label(label="Roxy LifePanel")
        title.add_css_class("title-1")
        title.set_xalign(0)
        title_box.append(title)

        self.status_strip = Gtk.Label(label="Loading live MOSCore truth...")
        self.status_strip.add_css_class("caption")
        self.status_strip.set_xalign(0)
        title_box.append(self.status_strip)

        self.overall_chip = Gtk.Label(label="--")
        self.overall_chip.add_css_class("moc-chip-info")
        self.overall_chip.set_valign(Gtk.Align.CENTER)
        title_row.append(self.overall_chip)

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        body.add_css_class("moc-mission-canvas")
        outer.append(body)

        # Left rail: first-class live objects.
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.add_css_class("moc-rail")
        left.set_size_request(270, -1)
        body.append(left)

        left_title = Gtk.Label(label="Domain Objects")
        left_title.add_css_class("moc-section-label")
        left_title.set_xalign(0)
        left.append(left_title)

        for key, label, page in [
            ("estate", "Roxy Estate", "overview"),
            ("agents", "Agents", "agents"),
            ("brain", "Brain Authority", "brain"),
            ("models", "Model Lanes", "brain"),
            ("mcp", "MCP Processes", "agents"),
            ("proof", "Receipts / Proof", "receipts"),
            ("storage", "Storage / Swap", "storage"),
            ("health", "Health Gate", "services"),
        ]:
            left.append(self._create_fact_row(key, label, page))

        # Center canvas: live summary instruments.
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        center.set_hexpand(True)
        body.append(center)

        self.alert_label = Gtk.Label(label="")
        self.alert_label.add_css_class("moc-panel")
        self.alert_label.set_xalign(0)
        self.alert_label.set_wrap(True)
        center.append(self.alert_label)

        grid_title = Gtk.Label(label="Estate Instruments")
        grid_title.add_css_class("moc-section-label")
        grid_title.set_xalign(0)
        center.append(grid_title)

        self.grid_box = Gtk.FlowBox()
        self.grid_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid_box.set_homogeneous(True)
        self.grid_box.set_min_children_per_line(2)
        self.grid_box.set_max_children_per_line(4)
        self.grid_box.set_column_spacing(12)
        self.grid_box.set_row_spacing(12)
        center.append(self.grid_box)

        cards = [
            ("performance", "Performance", "preferences-system-symbolic", "performance"),
            ("agents", "Agents", "applications-games-symbolic", "agents"),
            ("brain", "Brain", "preferences-system-symbolic", "brain"),
            ("executive", "Executive", "emblem-ok-symbolic", "executive"),
            ("content", "Action Ladder", "folder-music-symbolic", "content"),
            ("proof", "Proof", "emblem-ok-symbolic", "receipts"),
            ("storage", "Storage", "drive-harddisk-symbolic", "storage"),
            ("services", "Health Gate", "system-run-symbolic", "services"),
        ]

        for key, card_title, icon, page in cards:
            card = LifeCard(card_title, icon, on_click=lambda p=page: self._navigate(p))
            self._cards[key] = card
            self.grid_box.append(card)

        compact_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        compact_box.set_homogeneous(True)
        center.append(compact_box)

        for key, card_title, icon in [
            ("law0", "Law 0", "security-high-symbolic"),
            ("external_guard", "Guard", "drive-removable-media-symbolic"),
            ("thermal", "Thermal", "temperature-symbolic"),
            ("citadel", "Citadel", "network-workgroup-symbolic"),
        ]:
            card = LifeCard(card_title, icon)
            self._cards[key] = card
            compact_box.append(card)

        # Right inspector: procedures, risk, source age.
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.add_css_class("moc-inspector")
        right.set_size_request(310, -1)
        body.append(right)

        right_title = Gtk.Label(label="Procedure Inspector")
        right_title.add_css_class("moc-section-label")
        right_title.set_xalign(0)
        right.append(right_title)

        for key, label, page in [
            ("sentinel", "Inspect Sentinel", "alerts"),
            ("performance", "Stabilize Performance", "performance"),
            ("agents", "Review Agents", "agents"),
            ("brain", "Verify Brain", "brain"),
            ("storage", "Protect Storage", "storage"),
            ("proof", "Open Proof", "receipts"),
        ]:
            right.append(self._create_procedure_row(key, label, page))

        footer_title = Gtk.Label(label="Kernel Facts")
        footer_title.add_css_class("moc-section-label")
        footer_title.set_xalign(0)
        footer_title.set_margin_top(8)
        right.append(footer_title)

        self.source_label = Gtk.Label(label="Source: --")
        self.source_label.add_css_class("moc-row-subtitle")
        self.source_label.set_xalign(0)
        self.source_label.set_wrap(True)
        right.append(self.source_label)

        self.footer_label = Gtk.Label(label="")
        self.footer_label.add_css_class("monospace-small")
        self.footer_label.set_xalign(0)
        self.footer_label.set_wrap(True)
        right.append(self.footer_label)

    def _create_fact_row(self, key: str, title: str, page: Optional[str] = None) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row.add_css_class("moc-object-row")
        if page:
            click = Gtk.GestureClick()
            click.connect("pressed", lambda g, n, x, y, p=page: self._navigate(p))
            row.add_controller(click)
            row.set_cursor_from_name("pointer")

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("moc-row-title")
        title_label.set_xalign(0)
        row.append(title_label)

        value_label = Gtk.Label(label="--")
        value_label.add_css_class("moc-row-value")
        value_label.set_xalign(0)
        row.append(value_label)

        subtitle_label = Gtk.Label(label="")
        subtitle_label.add_css_class("moc-row-subtitle")
        subtitle_label.set_xalign(0)
        subtitle_label.set_wrap(True)
        row.append(subtitle_label)

        self._fact_rows[key] = {"row": row, "value": value_label, "subtitle": subtitle_label}
        return row

    def _create_procedure_row(self, key: str, title: str, page: Optional[str] = None) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        row.add_css_class("moc-procedure-row")
        if page:
            click = Gtk.GestureClick()
            click.connect("pressed", lambda g, n, x, y, p=page: self._navigate(p))
            row.add_controller(click)
            row.set_cursor_from_name("pointer")

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(top)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("moc-row-title")
        title_label.set_xalign(0)
        title_label.set_hexpand(True)
        top.append(title_label)

        chip = Gtk.Label(label="--")
        chip.add_css_class("moc-chip-info")
        top.append(chip)

        detail = Gtk.Label(label="")
        detail.add_css_class("moc-row-subtitle")
        detail.set_xalign(0)
        detail.set_wrap(True)
        row.append(detail)

        self._procedure_rows[key] = {"row": row, "chip": chip, "detail": detail}
        return row

    def _navigate(self, page: str):
        if self.on_navigate:
            self.on_navigate(page)

    def _set_fact(self, key: str, value: str, subtitle: str, status: str = "healthy"):
        item = self._fact_rows.get(key)
        if not item:
            return
        item["value"].set_label(value)
        item["subtitle"].set_label(subtitle)
        self._set_status_class(item["row"], status)

    def _set_procedure(self, key: str, state: str, detail: str, status: str = "healthy"):
        item = self._procedure_rows.get(key)
        if not item:
            return
        chip = item["chip"]
        chip.set_label(state)
        self._set_chip_class(chip, status)
        item["detail"].set_label(detail)
        self._set_status_class(item["row"], status)

    def _set_status_class(self, widget: Gtk.Widget, status: str):
        widget.remove_css_class("status-healthy")
        widget.remove_css_class("status-warn")
        widget.remove_css_class("status-blocked")
        if status in ("healthy", "warn", "blocked"):
            widget.add_css_class(f"status-{status}")

    def _set_chip_class(self, widget: Gtk.Widget, status: str):
        for cls in ("moc-chip-success", "moc-chip-warning", "moc-chip-danger", "moc-chip-info", "moc-chip-regent"):
            widget.remove_css_class(cls)
        css = {
            "healthy": "moc-chip-success",
            "warn": "moc-chip-warning",
            "blocked": "moc-chip-danger",
            "regent": "moc-chip-regent",
        }.get(status, "moc-chip-info")
        widget.add_css_class(css)

    def _status_for(self, value: str) -> str:
        normalized = str(value or "").lower()
        if normalized in ("red", "blocked", "error", "fail", "failed", "down"):
            return "blocked"
        if normalized in ("yellow", "warn", "warning", "degraded", "attention", "accumulating"):
            return "warn"
        return "healthy"

    def update(self, data: dict):
        """Update LifePanel cards. Sparklines only redraw when this page is visible."""
        perf = data.get("performance", {})
        agents = perf.get("agents", {})
        brain = data.get("brainAuthority", {})
        judge = data.get("judgeAuthority", {})
        closure = data.get("sovereignClosure", {})
        citadel = data.get("citadel", {})
        health_gate = data.get("healthGate", {})
        gateway = data.get("gateway", {})
        llm235 = data.get("llm235b", {})
        qdrant = data.get("qdrant", {})
        overall = data.get("overall", "?")
        operator_overall = data.get("operatorOverall", overall)
        next_action = data.get("nextAction", "") or "No owner action in current snapshot."
        generated_at = data.get("generatedAt", "unknown")

        is_visible = self.get_visible()

        # Top status.
        self.status_strip.set_label(f"Estate {overall} · Operator {operator_overall} · {generated_at}")
        status = self._status_for(operator_overall if operator_overall != "GREEN" else overall)
        self.overall_chip.set_label(f"OPERATOR {operator_overall}")
        self._set_chip_class(self.overall_chip, status)
        self.alert_label.set_label(next_action)
        self._set_status_class(self.alert_label, status)

        # Shared source values.
        cpu = perf.get("cpu", {})
        util = float(cpu.get("utilPct", 0) or 0)
        load1 = float(cpu.get("load1", 0) or 0)
        load5 = float(cpu.get("load5", 0) or 0)
        gpus = (perf.get("gpu") or {}).get("gpus", []) or data.get("gpus", [])
        gpu_count = len(gpus) or int((perf.get("gpu") or {}).get("count", 0) or 0)
        gpu_max_util = max((float(g.get("utilPct", g.get("utilization_pct", 0)) or 0) for g in gpus), default=0)
        gpu_hot = max((float(g.get("tempC", g.get("temp_c", 0)) or 0) for g in gpus), default=0)
        host_mem = data.get("hostMemory", {})
        ram = host_mem.get("ram", {})
        swap = host_mem.get("swap", {})
        ram_used = float(ram.get("usedGb", ram.get("used_gb", 0)) or 0)
        ram_total = float(ram.get("totalGb", ram.get("total_gb", 0)) or 0)
        ram_pct = (ram_used / ram_total * 100) if ram_total > 0 else 0
        swap_used = float(swap.get("swapUsedGb", swap.get("usedGb", 0)) or 0)
        swap_total = float(swap.get("swapTotalGb", swap.get("totalGb", 32)) or 32)
        swap_pct = (swap_used / swap_total * 100) if swap_total > 0 else 0
        mcp = perf.get("mcp", {})
        mcp_total = int(mcp.get("total", 0) or 0)
        mcp_counts = mcp.get("counts", {})
        top_mcp = max(mcp_counts.items(), key=lambda item: item[1])[0] if mcp_counts else "none"
        action_ladder = data.get("actionLadderSummary") or []
        action_done = sum(1 for item in action_ladder if str(item.get("gate", "")).lower() == "done")
        health_checks = health_gate.get("checks", {})
        health_pass = sum(1 for v in health_checks.values() if v == "pass")
        services = data.get("services") or {}

        # Left object rail.
        self._set_fact("estate", str(overall), f"Operator {operator_overall}", self._status_for(operator_overall))
        self._set_fact(
            "agents",
            f"{agents.get('active', 0)}/{agents.get('total', 0)}",
            f"{agents.get('abandoned', 0)} abandoned · {mcp_total} MCP",
            "blocked" if agents.get("abandoned", 0) > 5 else "warn" if agents.get("abandoned", 0) else "healthy",
        )
        self._set_fact(
            "brain",
            brain.get("verdict", "?"),
            f"{brain.get('realBrain', {}).get('messages', 0)} messages · Qdrant {qdrant.get('status', '?')}",
            self._status_for(brain.get("status", "")),
        )
        self._set_fact(
            "models",
            str(gateway.get("models", 0)),
            f"235B {'reachable' if llm235.get('reachable') else 'offline'} · port {gateway.get('port', 4000)}",
            "healthy" if gateway.get("status") == "healthy" and llm235.get("reachable") else "warn",
        )
        self._set_fact("mcp", str(mcp_total), f"Top group: {top_mcp}", "blocked" if mcp_total > 80 else "warn" if mcp_total > 50 else "healthy")
        self._set_fact(
            "proof",
            judge.get("verdict", "?"),
            f"Pass rate {judge.get('reputation', {}).get('passRate', 0):.0%}",
            self._status_for(judge.get("status", "")),
        )
        self._set_fact(
            "storage",
            f"{swap_pct:.0f}% swap",
            f"RAM {ram_used:.1f}/{ram_total:.0f} GB",
            "blocked" if swap_pct > 80 else "warn" if swap_pct > 50 else "healthy",
        )
        self._set_fact(
            "health",
            health_gate.get("status", "?"),
            f"{health_pass}/{len(health_checks)} checks pass",
            self._status_for(health_gate.get("status", "")),
        )

        # Center cards.
        coll = get_collector()

        if "performance" in self._cards:
            c = self._cards["performance"]
            perf_card_status = "blocked" if util > 80 else "warn" if perf.get("status") == "warn" or util > 60 else "healthy"
            c.set(f"{util:.0f}%", f"Load {load1:.1f} · GPU max {gpu_max_util:.0f}%", perf_card_status,
                  history=coll.get("cpu") if is_visible else None)

        if "agents" in self._cards:
            abandoned = int(agents.get("abandoned", 0) or 0)
            total = int(agents.get("total", 0) or 0)
            c = self._cards["agents"]
            c.set(str(total), f"{agents.get('active', 0)} active · {abandoned} abandoned",
                  "blocked" if abandoned > 5 else "warn" if abandoned else "healthy",
                  history=coll.get("agents") if is_visible else None)

        if "brain" in self._cards:
            brain_ok = brain.get("status") == "healthy"
            c = self._cards["brain"]
            c.set(brain.get("verdict", "?"), f"{gateway.get('models', 0)} models · Qdrant {qdrant.get('status', '?')}",
                  "healthy" if brain_ok else "warn")

        if "executive" in self._cards:
            campaigns = int(closure.get("campaignsConverged", 0) or 0)
            total_campaigns = int(closure.get("campaignsTotal", 1) or 1)
            c = self._cards["executive"]
            c.set(f"{campaigns}/{total_campaigns}", f"Sovereignty {closure.get('sovereignty', 0)}",
                  self._status_for(closure.get("status", "")))

        if "content" in self._cards:
            c = self._cards["content"]
            if action_ladder:
                c.set(f"{action_done}/{len(action_ladder)}", "Apex action ladder gates",
                      "healthy" if action_done == len(action_ladder) else "warn")
            else:
                c.set("n/a", "No action ladder in snapshot", "warn")

        if "proof" in self._cards:
            judge_ok = judge.get("status") == "healthy"
            c = self._cards["proof"]
            c.set(judge.get("verdict", "?"), "Judge authority", "healthy" if judge_ok else "warn")

        if "storage" in self._cards:
            c = self._cards["storage"]
            c.set(f"{swap_pct:.0f}%", f"Swap {swap_used:.1f}/{swap_total:.0f} GB",
                  "blocked" if swap_pct > 80 else "warn" if swap_pct > 50 else "healthy",
                  history=coll.get("swap") if is_visible else None)

        if "services" in self._cards:
            c = self._cards["services"]
            if services:
                healthy = sum(1 for s in services.values() if s.get("health") in ("ok", "healthy"))
                total_svcs = len(services)
                c.set(f"{healthy}/{total_svcs}", "Live system services",
                      "healthy" if healthy == total_svcs else "warn")
            else:
                c.set(health_gate.get("status", "?"), f"{health_pass}/{len(health_checks)} health checks",
                      self._status_for(health_gate.get("status", "")))

        roxy = data.get("roxy", {})
        law0_ok = roxy.get("law0_ok", False)
        if "law0" in self._cards:
            c = self._cards["law0"]
            c.set("PASS" if law0_ok else "FAIL", "Read-only gate", "healthy" if law0_ok else "blocked")

        guard_ok = roxy.get("external_guard_ok", False)
        if "external_guard" in self._cards:
            c = self._cards["external_guard"]
            c.set("PASS" if guard_ok else "FAIL", "External media", "healthy" if guard_ok else "blocked")

        idle = data.get("idle_health", {})
        temp = idle.get("temperature", {})
        hottest = float(temp.get("hottest_c", 0) or 0)
        if "thermal" in self._cards:
            c = self._cards["thermal"]
            c.set(f"{hottest:.0f}C", temp.get("status", "?").title(),
                  "blocked" if hottest > 80 else "warn" if hottest > 60 else "healthy")

        citadel_overall = citadel.get("overall", "?")
        if "citadel" in self._cards:
            c = self._cards["citadel"]
            c.set(citadel_overall, "Citadel status", self._status_for(citadel_overall))

        # Procedure inspector.
        self._set_procedure("sentinel", operator_overall, next_action, status)
        self._set_procedure("performance", perf.get("status", "?").upper(), f"CPU {util:.1f}% · load5 {load5:.1f} · GPU hot {gpu_hot:.0f}C", self._status_for(perf.get("status", "")))
        self._set_procedure("agents", f"{agents.get('abandoned', 0)} stuck", f"{agents.get('active', 0)} active of {agents.get('total', 0)} total", "blocked" if agents.get("abandoned", 0) > 5 else "warn" if agents.get("abandoned", 0) else "healthy")
        self._set_procedure("brain", brain.get("verdict", "?"), f"Brain {brain.get('status', '?')} · Qdrant {qdrant.get('status', '?')}", self._status_for(brain.get("status", "")))
        self._set_procedure("storage", f"{swap_pct:.0f}%", f"Swap {swap_used:.1f}/{swap_total:.0f} GB · RAM {ram_pct:.0f}%", "blocked" if swap_pct > 80 else "warn" if swap_pct > 50 else "healthy")
        self._set_procedure("proof", judge.get("verdict", "?"), judge.get("note", "")[:100], self._status_for(judge.get("status", "")))

        self.source_label.set_label(f"Source: ~/.roxy/apex-status.json · generated {generated_at}")
        self.footer_label.set_label(
            f"GPUs: {gpu_count} · MCP: {mcp_total} · "
            f"Agents: {agents.get('total', 0)} · Health checks: {health_pass}/{len(health_checks)}"
        )
