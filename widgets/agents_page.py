#!/usr/bin/env python3
"""
Agents Page — V5 Agent Operating Console

Displays live AgentContextPacketV1 instances with:
- Health scores, status, anomalies (stale, duplicate, blocked)
- Git state (HEAD, branch, dirty files)
- Process details (PID, CPU, MEM, TTY, session)
- MCP server attachments
- Lifecycle receipts
- Authority actions (refresh, check, export)

Primary acceptance:
When Mark opens Roxy Command Center, he can see exactly what every active
agent is doing, what it owns, whether it is safe, and what action Roxy
recommends next.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gdk
from typing import Optional, Dict, Any, List
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "services"))
from agent_discovery_service import AgentDiscoveryService, AgentContextPacketV1


# =============================================================================
# HEALTH BAR
# =============================================================================

class HealthBar(Gtk.Box):
    """Colored health score bar (0-100)."""
    
    def __init__(self, score: int = 0):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_size_request(80, 8)
        
        self._fill = Gtk.Box()
        self._fill.set_size_request(int(80 * score / 100), 8)
        self.append(self._fill)
        
        self._empty = Gtk.Box()
        self._empty.set_hexpand(True)
        self.append(self._empty)
        
        self.set_score(score)
    
    def set_score(self, score: int):
        self._fill.set_size_request(int(80 * score / 100), 8)
        self._fill.remove_css_class("health-good")
        self._fill.remove_css_class("health-warn")
        self._fill.remove_css_class("health-bad")
        
        if score >= 70:
            self._fill.add_css_class("health-good")
        elif score >= 40:
            self._fill.add_css_class("health-warn")
        else:
            self._fill.add_css_class("health-bad")


# =============================================================================
# AGENT CARD
# =============================================================================

class AgentCard(Gtk.Box):
    """Rich card showing a single AgentContextPacketV1."""
    
    def __init__(self, packet: AgentContextPacketV1, on_action: callable):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.packet = packet
        self._on_action = on_action
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.add_css_class("card")
        
        self._build_ui()
    
    def _build_ui(self):
        p = self.packet
        
        # Header row: icon + ID + lane badge + health bar
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)
        
        # Status icon
        status_icons = {
            "active": "🟢", "idle": "⚪", "stale": "🟤",
            "blocked": "🔴", "duplicate": "🟡", "unknown": "⚫"
        }
        icon = Gtk.Label(label=status_icons.get(p.status, "⚫"))
        header.append(icon)
        
        # Agent ID
        id_lbl = Gtk.Label(label=p.agent_id)
        id_lbl.add_css_class("heading")
        id_lbl.set_xalign(0)
        id_lbl.set_hexpand(True)
        header.append(id_lbl)
        
        # Lane badge
        if p.lane:
            lane_badge = Gtk.Label(label=p.lane.upper())
            lane_badge.add_css_class("caption")
            lane_badge.add_css_class("source-badge")
            lane_badge.add_css_class("source-daemon")
            header.append(lane_badge)
        
        # Health bar
        health_bar = HealthBar(p.health_score)
        header.append(health_bar)
        
        health_lbl = Gtk.Label(label=f"{p.health_score}")
        health_lbl.add_css_class("caption")
        health_lbl.set_size_request(28, -1)
        header.append(health_lbl)
        
        # Details grid
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details.set_margin_start(8)
        details.set_margin_top(4)
        self.append(details)
        
        # Row 1: Process info
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        details.append(row1)
        
        if p.pid:
            self._add_detail(row1, "PID", str(p.pid))
        if p.tty:
            self._add_detail(row1, "TTY", p.tty)
        if p.cpu_percent:
            self._add_detail(row1, "CPU", f"{p.cpu_percent:.1f}%")
        if p.mem_percent:
            self._add_detail(row1, "MEM", f"{p.mem_percent:.1f}%")
        if p.start_time:
            self._add_detail(row1, "Start", p.start_time)
        
        # Row 2: Session + MCPs
        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        details.append(row2)
        
        if p.session_type:
            self._add_detail(row2, "Session", f"{p.session_type}:{p.session_name}" if p.session_name else p.session_type)
        if p.child_count:
            self._add_detail(row2, "Children", str(p.child_count))
        if p.mcp_servers:
            mcp_text = ", ".join(p.mcp_servers[:3])
            if len(p.mcp_servers) > 3:
                mcp_text += f" +{len(p.mcp_servers)-3}"
            self._add_detail(row2, "MCPs", mcp_text)
        
        # Row 3: Git state
        if p.head_short or p.branch or p.dirty_count:
            row3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            details.append(row3)
            if p.head_short:
                self._add_detail(row3, "HEAD", p.head_short)
            if p.branch:
                self._add_detail(row3, "Branch", p.branch)
            if p.dirty_count:
                dirty_lbl = self._add_detail(row3, "Dirty", str(p.dirty_count))
                if p.dirty_count > 20:
                    dirty_lbl.add_css_class("warning")
        
        # Row 4: Activity + receipt
        if p.last_activity_age_seconds or p.last_receipt:
            row4 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            details.append(row4)
            if p.last_activity_age_seconds:
                age_text = self._format_age(p.last_activity_age_seconds)
                self._add_detail(row4, "Last activity", age_text)
            if p.last_receipt:
                receipt_file = p.last_receipt.get("_file", "")
                receipt_name = Path(receipt_file).name if receipt_file else "unknown"
                self._add_detail(row4, "Receipt", receipt_name)
        
        # Blocked / anomaly banner
        if p.blocked_reason:
            banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            banner.set_margin_top(4)
            banner.set_margin_start(8)
            banner.set_margin_end(8)
            banner.add_css_class("linked")
            self.append(banner)
            
            warn_icon = Gtk.Label(label="⚠️")
            banner.append(warn_icon)
            
            warn_text = Gtk.Label(label=p.blocked_reason)
            warn_text.add_css_class("caption")
            warn_text.add_css_class("warning")
            warn_text.set_xalign(0)
            warn_text.set_hexpand(True)
            warn_text.set_wrap(True)
            banner.append(warn_text)
        
        # Next action recommendation
        if p.next_action:
            action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            action_box.set_margin_start(8)
            action_box.set_margin_top(4)
            self.append(action_box)
            
            action_icon = Gtk.Label(label="➡️")
            action_box.append(action_icon)
            
            action_text = Gtk.Label(label=p.next_action)
            action_text.add_css_class("caption")
            action_text.add_css_class("suggested-action")
            action_text.set_xalign(0)
            action_text.set_hexpand(True)
            action_text.set_wrap(True)
            action_box.append(action_text)
        
        # Action buttons
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        actions.set_margin_start(8)
        actions.set_margin_top(8)
        self.append(actions)
        
        for label, action_key in [
            ("🔍 Check", "check"),
            ("🔄 Refresh", "refresh"),
            ("📤 Receipt", "receipt"),
            ("💻 Terminal", "terminal"),
        ]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("flat")
            btn.add_css_class("caption")
            btn.connect("clicked", lambda _b, ak=action_key: self._on_action(ak, self.packet))
            actions.append(btn)
    
    def _add_detail(self, parent: Gtk.Box, label: str, value: str) -> Gtk.Label:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        parent.append(box)
        
        lbl = Gtk.Label(label=f"{label}:")
        lbl.add_css_class("caption")
        lbl.add_css_class("dim-label")
        box.append(lbl)
        
        val = Gtk.Label(label=value)
        val.add_css_class("caption")
        val.set_xalign(0)
        box.append(val)
        return val
    
    @staticmethod
    def _format_age(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds//60}m ago"
        if seconds < 86400:
            return f"{seconds//3600}h ago"
        return f"{seconds//86400}d ago"


# =============================================================================
# AGENTS PAGE — V5 Agent Operating Console
# =============================================================================

class AgentsPage(Gtk.ScrolledWindow):
    """V5 Agent Operating Console — visible authority surface for live agents."""
    
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._discovery = AgentDiscoveryService()
        self._packets: List[AgentContextPacketV1] = []
        self._cards: List[AgentCard] = []
        self._filter_status = "all"
        self._build_ui()
        
        # Auto-refresh every 30s
        GLib.timeout_add_seconds(30, self._on_auto_refresh)
    
    def _build_ui(self):
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.set_margin_top(24)
        self.main_box.set_margin_bottom(24)
        self.main_box.set_margin_start(24)
        self.main_box.set_margin_end(24)
        self.set_child(self.main_box)
        
        # Title
        title = Gtk.Label(label="🤖 Agent Operating Console")
        title.add_css_class("title-1")
        title.set_xalign(0)
        self.main_box.append(title)
        
        subtitle = Gtk.Label(label="Live authority surface for visible agents")
        subtitle.add_css_class("dim-label")
        subtitle.set_xalign(0)
        subtitle.set_margin_bottom(16)
        self.main_box.append(subtitle)
        
        # Summary bar
        self.summary_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.summary_box.set_margin_bottom(16)
        self.main_box.append(self.summary_box)
        
        self._summary_cards: Dict[str, Gtk.Box] = {}
        for label in ["Total", "Active", "Idle", "Stale", "Blocked", "Duplicate", "Health"]:
            card = self._make_summary_card(label)
            self._summary_cards[label.lower()] = card
            self.summary_box.append(card)
        
        # Filter bar
        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filter_box.set_margin_bottom(16)
        self.main_box.append(filter_box)
        
        filter_label = Gtk.Label(label="Filter:")
        filter_label.add_css_class("dim-label")
        filter_box.append(filter_label)
        
        self._filter_buttons: Dict[str, Gtk.ToggleButton] = {}
        for status in ["all", "active", "idle", "stale", "blocked", "duplicate"]:
            btn = Gtk.ToggleButton(label=status.title())
            btn.add_css_class("caption")
            btn.add_css_class("pill")
            if status == "all":
                btn.set_active(True)
            btn.connect("toggled", self._on_filter_toggled, status)
            self._filter_buttons[status] = btn
            filter_box.append(btn)
        
        # Action bar
        action_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_bar.set_margin_bottom(16)
        self.main_box.append(action_bar)
        
        self.scan_btn = Gtk.Button(label="🔍 Scan Now")
        self.scan_btn.add_css_class("suggested-action")
        self.scan_btn.connect("clicked", self._on_scan)
        action_bar.append(self.scan_btn)
        
        self.export_btn = Gtk.Button(label="📤 Export Packets")
        self.export_btn.add_css_class("flat")
        self.export_btn.connect("clicked", self._on_export)
        action_bar.append(self.export_btn)
        
        self.check_git_btn = Gtk.Button(label="🌿 Check Git")
        self.check_git_btn.add_css_class("flat")
        self.check_git_btn.connect("clicked", self._on_check_git)
        action_bar.append(self.check_git_btn)
        
        self.hardware_btn = Gtk.Button(label="🖥️ Hardware Report")
        self.hardware_btn.add_css_class("flat")
        self.hardware_btn.connect("clicked", self._on_hardware_report)
        action_bar.append(self.hardware_btn)
        
        self._status_label = Gtk.Label(label="Click Scan Now to discover agents")
        self._status_label.add_css_class("caption")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_margin_start(12)
        action_bar.append(self._status_label)
        
        # Cards container
        self.cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.append(self.cards_box)
        
        # Diagnose output (legacy)
        self.diagnose_output = Gtk.Label(label="")
        self.diagnose_output.add_css_class("monospace-small")
        self.diagnose_output.set_xalign(0)
        self.diagnose_output.set_wrap(True)
        self.diagnose_output.set_margin_top(16)
        self.main_box.append(self.diagnose_output)
    
    def _make_summary_card(self, title: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("overview-card")
        box.set_size_request(80, -1)
        
        t = Gtk.Label(label=title)
        t.add_css_class("overview-title")
        t.set_xalign(0)
        box.append(t)
        
        v = Gtk.Label(label="—")
        v.add_css_class("overview-value")
        v.set_xalign(0)
        box.append(v)
        
        return box
    
    def _set_summary(self, key: str, value: str, status: str = "healthy"):
        card = self._summary_cards.get(key)
        if not card:
            return
        child = card.get_first_child()
        if child:
            child = child.get_next_sibling()
            if child:
                child.set_label(value)
        
        for s in ["healthy", "warn", "blocked"]:
            card.remove_css_class(f"status-{s}")
        if status in ["healthy", "warn", "blocked"]:
            card.add_css_class(f"status-{status}")
    
    def _on_filter_toggled(self, btn, status: str):
        if btn.get_active():
            self._filter_status = status
            # Deactivate others
            for s, b in self._filter_buttons.items():
                if s != status:
                    b.set_active(False)
            self._refresh_cards()
    
    def _on_scan(self, btn):
        self.scan_btn.set_sensitive(False)
        self._status_label.set_label("Scanning...")
        
        def do_scan():
            self._packets = self._discovery.scan()
            self._update_summary()
            self._refresh_cards()
            self.scan_btn.set_sensitive(True)
            self._status_label.set_label(f"Last scan: {len(self._packets)} agents")
            return False
        
        GLib.idle_add(do_scan)
    
    def _on_auto_refresh(self):
        self._packets = self._discovery.scan()
        self._update_summary()
        self._refresh_cards()
        self._status_label.set_label(f"Auto-refreshed: {len(self._packets)} agents")
        return True  # Keep timeout active
    
    def _update_summary(self):
        summary = self._discovery.get_summary()
        
        self._set_summary("total", str(summary.get("total_agents", 0)))
        self._set_summary("active", str(summary.get("by_status", {}).get("active", 0)))
        self._set_summary("idle", str(summary.get("by_status", {}).get("idle", 0)))
        self._set_summary("stale", str(summary.get("stale_count", 0)),
                          "blocked" if summary.get("stale_count", 0) > 0 else "healthy")
        self._set_summary("blocked", str(summary.get("blocked_count", 0)),
                          "blocked" if summary.get("blocked_count", 0) > 0 else "healthy")
        self._set_summary("duplicate", str(summary.get("duplicate_count", 0)),
                          "warn" if summary.get("duplicate_count", 0) > 0 else "healthy")
        self._set_summary("health", f"{summary.get('avg_health', 0):.0f}")
    
    def _refresh_cards(self):
        # Remove old cards
        while self.cards_box.get_first_child():
            self.cards_box.remove(self.cards_box.get_first_child())
        self._cards = []
        
        # Filter
        filtered = self._packets
        if self._filter_status != "all":
            filtered = [p for p in filtered if p.status == self._filter_status]
        
        # Sort by health (worst first)
        filtered = sorted(filtered, key=lambda p: p.health_score)
        
        for packet in filtered:
            card = AgentCard(packet, self._on_agent_action)
            self._cards.append(card)
            self.cards_box.append(card)
        
        if not filtered:
            empty = Gtk.Label(label="No agents match the current filter.")
            empty.add_css_class("dim-label")
            empty.set_margin_top(24)
            self.cards_box.append(empty)
    
    def _on_agent_action(self, action: str, packet: AgentContextPacketV1):
        if action == "check":
            self.diagnose_output.set_label(f"Checking {packet.agent_id}...")
            # TODO: Implement check action
        elif action == "refresh":
            self.diagnose_output.set_label(f"Refreshing context for {packet.agent_id}...")
            # TODO: Implement refresh action
        elif action == "receipt":
            if packet.last_receipt:
                file_path = packet.last_receipt.get("_file", "")
                self.diagnose_output.set_label(f"Receipt: {file_path}")
            else:
                self.diagnose_output.set_label(f"No receipt found for {packet.agent_id}")
        elif action == "terminal":
            if packet.session_type == "tmux" and packet.session_name:
                parts = packet.session_name.split(":")
                if len(parts) == 2:
                    session, window = parts
                    cmd = f"tmux switch-client -t {session}:{window}"
                    self.diagnose_output.set_label(f"Terminal: {cmd}")
            else:
                self.diagnose_output.set_label(f"PID {packet.pid}: no tmux session")
    
    def _on_export(self, btn):
        if not self._packets:
            self.diagnose_output.set_label("No packets to export. Run Scan Now first.")
            return
        
        import json
        from pathlib import Path
        export_dir = Path.home() / ".config" / "roxy-command-center" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        
        ts = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
        path = export_dir / f"agent-packets-{ts}.json"
        path.write_text(json.dumps([p.to_dict() for p in self._packets], indent=2, default=str))
        
        self.diagnose_output.set_label(f"Exported {len(self._packets)} packets to {path}")
    
    def _on_check_git(self, btn):
        git_state = self._discovery._read_git_state()
        dirty = git_state.get("dirty_files", [])
        head = git_state.get("head", "")[:12]
        branch = git_state.get("branch", "")
        
        lines = [f"HEAD: {head} | Branch: {branch} | Dirty: {len(dirty)} files"]
        for f in dirty[:10]:
            lines.append(f"  {f}")
        if len(dirty) > 10:
            lines.append(f"  ... and {len(dirty)-10} more")
        
        self.diagnose_output.set_label("\n".join(lines))
    
    def _on_hardware_report(self, btn):
        try:
            import subprocess
            result = subprocess.run(
                ["uname", "-a"],
                capture_output=True, text=True, timeout=5
            )
            kernel = result.stdout.strip()
            
            result = subprocess.run(
                ["nproc"], capture_output=True, text=True, timeout=5
            )
            cpus = result.stdout.strip()
            
            result = subprocess.run(
                ["free", "-h"], capture_output=True, text=True, timeout=5
            )
            mem = result.stdout.strip()
            
            lines = [f"Kernel: {kernel}", f"CPUs: {cpus}", "Memory:", mem]
            self.diagnose_output.set_label("\n".join(lines))
        except Exception as e:
            self.diagnose_output.set_label(f"Hardware report failed: {e}")
    
    # Legacy update() for backward compatibility with telemetry flow
    def update(self, data: dict):
        pass  # V5 uses on-demand scanning instead of daemon data
