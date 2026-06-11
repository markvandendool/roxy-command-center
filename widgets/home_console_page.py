#!/usr/bin/env python3
"""
Home Console Page - The ROXY Command Center cockpit.

NORTH STAR: Home = Talk + Triage + Execute
- Not a dashboard. An operations console.
- GTK is thin client; current review build uses local Ollama directly.

Layout:
  [Left: Triage/Inbox]  [Center: Roxy Chat]  [Right: Progressions/Runs]

Chat is wired to local Ollama through ChatService.
Voice is Option B: Speak button toggle (not auto-speak).
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Pango
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import random
import sys
import os
import uuid

# Add parent dir to path for services import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.chat_service import (
    ChatService, VoiceService,
    ChatMessage as ServiceChatMessage,
    ChatMode, ConnectionStatus,
    Identity as ServiceIdentity,
    get_chat_service, get_voice_service
)
from services.orchestrator_truth_provider import OrchestratorTruthProvider
from widgets.operator_safety_rail import OperatorSafetyRail
from widgets.truth_badge import TruthBadge, TruthBadgeGroup
from services.factory_truth_service import get_factory_truth_service



# =============================================================================
# DATA MODELS (Canonical Schema - matches FINISHING_PLAN.md)
# =============================================================================

class Identity(Enum):
    """User identity for routing."""
    ME = "me"           # 👤 Personal
    MINDSONG = "mindsong"  # 🎵 Brand


class Bucket(Enum):
    """Triage bucket for inbox items."""
    NOW = "now"         # Requires immediate reply
    QUEUED = "queued"   # Can wait, but needs response
    FYI = "fyi"         # No reply needed


class RunStatus(Enum):
    """Execution run status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class InboxThread:
    """A thread in the unified inbox."""
    id: str
    source: str         # email, github, discord, instagram, etc.
    source_icon: str    # GTK icon name
    identity: Identity
    sender: str
    preview: str
    bucket: Bucket
    priority: int       # 0=P0 (critical), 1=P1, 2=P2
    timestamp: datetime
    unread: bool = True
    suggested_action: str = "Reply"  # Reply, Approve, Run, Ignore


@dataclass
class ExecutionRun:
    """A progression/run in the execution timeline."""
    id: str
    name: str
    type: str           # orchestrator, content_pipeline, deployment
    status: RunStatus
    started_at: Optional[datetime]
    progress_pct: Optional[int]
    can_cancel: bool = True


@dataclass
class ChatMessage:
    """A message in the Roxy conversation."""
    id: str
    role: str           # "user" or "assistant" or "system"
    content: str
    timestamp: datetime
    # Roxy harness metadata
    latency_ms: int = 0
    model: str = ""
    memory_refs: List[str] = None
    proposed_actions: List[str] = None
    # Context Inspector metadata (JARVIS Context Kernel)
    context_hash: str = ""
    context_kernel_version: str = ""
    context_kernel_hash: str = ""
    context_kernel: Dict[str, Any] = None
    source_health: Dict[str, Any] = None
    token_budget: Dict[str, Any] = None
    orico_counts: Dict[str, Any] = None
    degraded_reasons: List[str] = None
    harness_bypassed: bool = False

    def __post_init__(self):
        if self.memory_refs is None:
            self.memory_refs = []
        if self.proposed_actions is None:
            self.proposed_actions = []
        if self.source_health is None:
            self.source_health = {}
        if self.context_kernel is None:
            self.context_kernel = {}
        if self.token_budget is None:
            self.token_budget = {}
        if self.orico_counts is None:
            self.orico_counts = {}
        if self.degraded_reasons is None:
            self.degraded_reasons = []


# =============================================================================
# MOCK DATA STORE REMOVED — replaced by OrchestratorTruthProvider
# =============================================================================


# =============================================================================
# UI COMPONENTS
# =============================================================================

class IdentityChip(Gtk.Button):
    """Filter chip for identity selection."""
    
    def __init__(self, label: str, icon: str, identity: Optional[Identity], active: bool = False):
        super().__init__()
        self.identity = identity
        self.add_css_class("flat")
        self.add_css_class("identity-chip")
        if active:
            self.add_css_class("suggested-action")
        
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.set_child(box)
        
        icon_widget = Gtk.Label(label=icon)
        box.append(icon_widget)
        
        label_widget = Gtk.Label(label=label)
        box.append(label_widget)


class BucketTabs(Gtk.Box):
    """Now / Queued / FYI tab selector."""
    
    def __init__(self, on_bucket_change: Optional[callable] = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("linked")
        self.on_bucket_change = on_bucket_change
        self._buttons: Dict[Bucket, Gtk.ToggleButton] = {}
        self._current = Bucket.NOW
        
        for bucket in Bucket:
            btn = Gtk.ToggleButton(label=bucket.value.upper())
            btn.set_active(bucket == self._current)
            btn.connect("toggled", self._on_toggle, bucket)
            self._buttons[bucket] = btn
            self.append(btn)
    
    def _on_toggle(self, button: Gtk.ToggleButton, bucket: Bucket):
        if button.get_active():
            self._current = bucket
            for b, btn in self._buttons.items():
                if b != bucket:
                    btn.set_active(False)
            if self.on_bucket_change:
                self.on_bucket_change(bucket)


class InboxThreadRow(Gtk.ListBoxRow):
    """A single thread row in the inbox."""
    
    def __init__(self, thread: InboxThread):
        super().__init__()
        self.thread = thread
        self.add_css_class("inbox-thread-row")
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_box.set_margin_top(8)
        main_box.set_margin_bottom(8)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        self.set_child(main_box)
        
        # Top row: source icon, identity, sender, priority
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        main_box.append(top_row)
        
        # Source icon
        source_icon = Gtk.Image.new_from_icon_name(thread.source_icon)
        source_icon.set_pixel_size(16)
        source_icon.add_css_class("dim-label")
        top_row.append(source_icon)
        
        # Identity badge
        identity_label = Gtk.Label(label="👤" if thread.identity == Identity.ME else "🎵")
        identity_label.set_tooltip_text("Personal" if thread.identity == Identity.ME else "MindSong")
        top_row.append(identity_label)
        
        # Sender
        sender_label = Gtk.Label(label=thread.sender)
        sender_label.set_xalign(0)
        sender_label.set_hexpand(True)
        sender_label.add_css_class("heading")
        if thread.unread:
            sender_label.add_css_class("accent")
        top_row.append(sender_label)
        
        # Priority badge
        if thread.priority == 0:
            priority_label = Gtk.Label(label="P0")
            priority_label.add_css_class("error")
            top_row.append(priority_label)
        elif thread.priority == 1:
            priority_label = Gtk.Label(label="P1")
            priority_label.add_css_class("warning")
            top_row.append(priority_label)
        
        # Preview text
        preview_label = Gtk.Label(label=thread.preview)
        preview_label.set_xalign(0)
        preview_label.set_ellipsize(Pango.EllipsizeMode.END)
        preview_label.add_css_class("dim-label")
        main_box.append(preview_label)
        
        # Action buttons row
        actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions_row.set_margin_top(4)
        main_box.append(actions_row)
        
        # Suggested action button
        action_btn = Gtk.Button(label=thread.suggested_action)
        action_btn.add_css_class("suggested-action")
        action_btn.add_css_class("pill")
        action_btn.connect("clicked", self._on_action)
        actions_row.append(action_btn)
        
        # Secondary actions
        defer_btn = Gtk.Button(label="Defer")
        defer_btn.add_css_class("flat")
        defer_btn.add_css_class("dim-label")
        actions_row.append(defer_btn)
        
        roxy_btn = Gtk.Button(label="→ Roxy")
        roxy_btn.add_css_class("flat")
        roxy_btn.add_css_class("dim-label")
        roxy_btn.set_tooltip_text("Assign to Roxy")
        actions_row.append(roxy_btn)
    
    def _on_action(self, button):
        """Handle action click — log and show feedback."""
        print(f"[Inbox] Action '{self.thread.suggested_action}' on thread {self.thread.id}")
        # For now: show a transient dialog since full orchestration API is not yet wired
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"Action: {self.thread.suggested_action}",
        )
        dialog.set_secondary_text(f"Thread: {self.thread.sender}\nPreview: {self.thread.preview[:80]}\n\nFull orchestration API not yet wired — logged for owner review.")
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()


class TriageColumn(Gtk.Box):
    """Left column: Unified Inbox / Triage."""
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("triage-column")
        self.set_size_request(320, -1)
        
        self._current_identity: Optional[Identity] = None
        self._current_bucket = Bucket.NOW
        self._threads: List[InboxThread] = []
        
        self._build_ui()
        self._load_data()
    
    def _build_ui(self):
        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_bottom(8)
        self.append(header)
        
        # Title
        title = Gtk.Label(label="Inbox")
        title.add_css_class("title-2")
        title.set_xalign(0)
        header.append(title)
        
        # Identity filter chips
        identity_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.append(identity_box)
        
        all_chip = IdentityChip("All", "📬", None, active=True)
        all_chip.connect("clicked", self._on_identity_filter, None)
        identity_box.append(all_chip)
        
        me_chip = IdentityChip("Me", "👤", Identity.ME)
        me_chip.connect("clicked", self._on_identity_filter, Identity.ME)
        identity_box.append(me_chip)
        
        mindsong_chip = IdentityChip("MindSong", "🎵", Identity.MINDSONG)
        mindsong_chip.connect("clicked", self._on_identity_filter, Identity.MINDSONG)
        identity_box.append(mindsong_chip)
        
        # Bucket tabs
        self.bucket_tabs = BucketTabs(on_bucket_change=self._on_bucket_change)
        header.append(self.bucket_tabs)
        
        # Thread list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled)
        
        self.thread_list = Gtk.ListBox()
        self.thread_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.thread_list.add_css_class("navigation-sidebar")
        scrolled.set_child(self.thread_list)
        
        # Super reply bar
        reply_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        reply_box.set_margin_start(12)
        reply_box.set_margin_end(12)
        reply_box.set_margin_bottom(12)
        self.append(reply_box)
        
        reply_label = Gtk.Label(label="Super Reply")
        reply_label.add_css_class("dim-label")
        reply_label.add_css_class("caption")
        reply_label.set_xalign(0)
        reply_box.append(reply_label)
        
        reply_entry = Gtk.Entry()
        reply_entry.set_placeholder_text("Type to reply to selected...")
        reply_box.append(reply_entry)
    
    def _on_identity_filter(self, button, identity: Optional[Identity]):
        self._current_identity = identity
        self._refresh_list()
    
    def _on_bucket_change(self, bucket: Bucket):
        self._current_bucket = bucket
        self._refresh_list()
    
    def _load_data(self):
        """Load inbox threads from canonical sources."""
        raw_threads = OrchestratorTruthProvider.get_inbox_threads()
        self._threads = [
            InboxThread(
                id=t["id"],
                source=t["source"],
                source_icon=t["source_icon"],
                identity=Identity.MINDSONG if t["identity"] == "mindsong" else Identity.ME,
                sender=t["sender"],
                preview=t["preview"],
                bucket=Bucket.NOW if t["bucket"] == "now" else Bucket.QUEUED if t["bucket"] == "queued" else Bucket.FYI,
                priority=t["priority"],
                timestamp=t["timestamp"],
                unread=t.get("unread", True),
                suggested_action=t.get("suggested_action", "Review"),
            )
            for t in raw_threads
        ]
        self._refresh_list()
    
    def _refresh_list(self):
        # Clear
        while True:
            row = self.thread_list.get_row_at_index(0)
            if row:
                self.thread_list.remove(row)
            else:
                break
        
        # Filter and add
        for thread in self._threads:
            # Identity filter
            if self._current_identity and thread.identity != self._current_identity:
                continue
            # Bucket filter
            if thread.bucket != self._current_bucket:
                continue
            
            row = InboxThreadRow(thread)
            self.thread_list.append(row)


class ChatMessage_Widget(Gtk.Box):
    """A single chat message bubble."""
    
    def __init__(self, message: ChatMessage):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_margin_top(8)
        self.set_margin_start(12)
        self.set_margin_end(12)

        def _display_text(value: Any) -> str:
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                parts = []
                for key in ("id", "type", "source", "title", "label", "path", "content", "text"):
                    item = value.get(key)
                    if item:
                        parts.append(f"{key}={item}")
                return " | ".join(parts) if parts else str(value)
            return str(value)
        
        if message.role == "system":
            self.add_css_class("system-message")
            label = Gtk.Label(label=message.content)
            label.add_css_class("dim-label")
            label.add_css_class("caption")
            label.set_wrap(True)
            label.set_xalign(0.5)
            label.set_selectable(True)  # Enable text selection
            self.append(label)
        else:
            is_user = message.role == "user"
            
            # Message bubble
            bubble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            bubble.add_css_class("chat-bubble")
            bubble.add_css_class("user-bubble" if is_user else "assistant-bubble")
            bubble.set_margin_start(50 if is_user else 0)
            bubble.set_margin_end(0 if is_user else 50)
            self.append(bubble)
            
            # Header row: role + metadata chips
            header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            header_row.set_margin_bottom(2)
            bubble.append(header_row)
            
            role_label = Gtk.Label(label="You" if is_user else "Roxy")
            role_label.add_css_class("caption")
            role_label.add_css_class("dim-label")
            role_label.set_xalign(0)
            header_row.append(role_label)
            
            if not is_user:
                # Model chip
                if message.model:
                    short_model = message.model.replace("roxy-coder-frontier", "ROXY").split(":")[0][:12]
                    model_chip = Gtk.Label(label=f"🧠 {short_model}")
                    model_chip.add_css_class("caption")
                    model_chip.add_css_class("dim-label")
                    model_chip.set_xalign(0)
                    header_row.append(model_chip)
                
                # Latency chip
                if message.latency_ms:
                    lat_chip = Gtk.Label(label=f"⏱️ {message.latency_ms}ms")
                    lat_chip.add_css_class("caption")
                    lat_chip.add_css_class("dim-label")
                    lat_chip.set_xalign(0)
                    header_row.append(lat_chip)
                
                # Memory refs chip
                if message.memory_refs:
                    refs_chip = Gtk.Label(label=f"🧩 {len(message.memory_refs)} refs")
                    refs_chip.add_css_class("caption")
                    refs_chip.add_css_class("dim-label")
                    refs_chip.set_xalign(0)
                    header_row.append(refs_chip)
                
                # Context hash chip
                if message.context_hash:
                    hash_chip = Gtk.Label(label=f"🔐 {message.context_hash[:8]}")
                    hash_chip.add_css_class("caption")
                    hash_chip.add_css_class("dim-label")
                    hash_chip.set_xalign(0)
                    hash_chip.set_tooltip_text(f"Context hash: {message.context_hash}")
                    header_row.append(hash_chip)
                
                # Context kernel version chip
                if message.context_kernel_version:
                    kv_chip = Gtk.Label(label=f"📦 v{message.context_kernel_version}")
                    kv_chip.add_css_class("caption")
                    kv_chip.add_css_class("dim-label")
                    kv_chip.set_xalign(0)
                    kv_chip.set_tooltip_text(f"Context Kernel version: {message.context_kernel_version}")
                    header_row.append(kv_chip)

                # Context kernel hash chip
                if message.context_kernel_hash:
                    kh_chip = Gtk.Label(label=f"🧬 {message.context_kernel_hash[:8]}")
                    kh_chip.add_css_class("caption")
                    kh_chip.add_css_class("dim-label")
                    kh_chip.set_xalign(0)
                    kh_chip.set_tooltip_text(f"Context Kernel hash: {message.context_kernel_hash}")
                    header_row.append(kh_chip)
                
                # Degraded / bypass warning chip
                if message.harness_bypassed:
                    warn_chip = Gtk.Label(label="⚠️ BYPASS")
                    warn_chip.add_css_class("caption")
                    warn_chip.add_css_class("error")
                    warn_chip.set_xalign(0)
                    header_row.append(warn_chip)
                elif message.degraded_reasons:
                    deg_chip = Gtk.Label(label=f"⚠️ {len(message.degraded_reasons)} degraded")
                    deg_chip.add_css_class("caption")
                    deg_chip.add_css_class("warning")
                    deg_chip.set_xalign(0)
                    deg_chip.set_tooltip_text("\n".join(message.degraded_reasons))
                    header_row.append(deg_chip)
            
            # Content - SELECTABLE for copy/paste
            content_label = Gtk.Label(label=message.content)
            content_label.set_wrap(True)
            content_label.set_xalign(0)
            content_label.set_max_width_chars(60)
            content_label.set_selectable(True)  # Enable text selection
            bubble.append(content_label)
            
            # Proposed actions row (assistant only)
            if not is_user and message.proposed_actions:
                actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                actions_box.set_margin_top(4)
                actions_box.add_css_class("linked")
                bubble.append(actions_box)
                
                for action in message.proposed_actions:
                    btn = Gtk.Button(label=f"⚡ {action}")
                    btn.add_css_class("suggested-action")
                    btn.add_css_class("pill")
                    btn.add_css_class("caption")
                    btn.set_tooltip_text(f"Proposed action: {action}")
                    actions_box.append(btn)
            
            # Context Inspector evidence row (assistant only) — Phase 2: Expandable details
            if not is_user and (
                message.context_hash
                or message.context_kernel_hash
                or message.orico_counts
                or message.token_budget
                or message.source_health
                or message.context_kernel
            ):
                evidence_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                evidence_frame.set_margin_top(6)
                evidence_frame.set_margin_start(4)
                evidence_frame.set_margin_end(4)
                evidence_frame.set_margin_bottom(4)
                bubble.append(evidence_frame)
                
                # --- Toggle header row ---
                toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                toggle_row.add_css_class("linked")
                evidence_frame.append(toggle_row)

                # Expand/collapse button stays first so it cannot be pushed out
                # of the narrow operator pane by long evidence summaries.
                expand_btn = Gtk.Button(label="🔍")
                expand_btn.add_css_class("flat")
                expand_btn.add_css_class("caption")
                expand_btn.set_size_request(40, -1)
                expand_btn.set_tooltip_text("Expand Context Inspector details")
                toggle_row.append(expand_btn)
                
                # Compact summary chips (always visible)
                summary = []
                if message.context_hash:
                    summary.append(f"🔐 {message.context_hash[:6]}")
                if message.context_kernel_hash:
                    summary.append(f"🧬 {message.context_kernel_hash[:6]}")
                if message.orico_counts:
                    summary.append(f"📦 ORICO {message.orico_counts.get('safeProvisional', 0)}")
                if message.token_budget and message.token_budget.get('estimatedPromptTokens'):
                    summary.append(f"📝 {message.token_budget['estimatedPromptTokens']}tk")
                if message.degraded_reasons:
                    summary.append(f"⚠️ {len(message.degraded_reasons)} degraded")
                elif message.harness_bypassed:
                    summary.append("⚠️ BYPASS")
                
                summary_label = Gtk.Label(label="  ".join(summary) if summary else "📊 Evidence")
                summary_label.add_css_class("caption")
                summary_label.add_css_class("dim-label")
                summary_label.set_xalign(0)
                summary_label.set_hexpand(True)
                summary_label.set_ellipsize(Pango.EllipsizeMode.END)
                toggle_row.append(summary_label)
                
                # --- Expandable detail panel (Gtk.Revealer) ---
                revealer = Gtk.Revealer()
                revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
                revealer.set_transition_duration(200)
                revealer.set_reveal_child(False)
                expand_btn.set_label("🔍")
                expand_btn.set_tooltip_text("Expand Context Inspector details")
                evidence_frame.append(revealer)
                
                detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                detail_box.set_margin_top(6)
                detail_box.set_margin_start(8)
                detail_box.set_margin_end(8)
                detail_box.set_margin_bottom(6)
                revealer.set_child(detail_box)
                
                def _build_detail_row(label_text: str, value_text: Any, icon: str = "", warning: bool = False):
                    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                    row.set_margin_start(4)
                    lbl = Gtk.Label(label=f"{icon} {label_text}" if icon else label_text)
                    lbl.add_css_class("caption")
                    lbl.add_css_class("dim-label")
                    lbl.set_xalign(0)
                    lbl.set_size_request(120, -1)
                    row.append(lbl)
                    val = Gtk.Label(label=_display_text(value_text))
                    val.add_css_class("caption")
                    val.set_xalign(0)
                    val.set_selectable(True)
                    if warning:
                        val.add_css_class("warning")
                    row.append(val)
                    return row
                
                # Section: Context Identity
                detail_box.append(_build_detail_row("Hash", message.context_hash or "—", "🔐"))
                detail_box.append(_build_detail_row("Kernel", message.context_kernel_version or "—", "📦"))
                if message.context_kernel_hash:
                    detail_box.append(_build_detail_row("Kernel Hash", message.context_kernel_hash, "🧬"))

                if message.context_kernel:
                    kernel_keys = ", ".join(sorted(message.context_kernel.keys())[:10]) or "—"
                    detail_box.append(_build_detail_row("Packet Keys", kernel_keys, "🧾"))

                # Section: Source Health
                source_health = message.source_health or {}
                if not source_health and message.context_kernel:
                    source_health = message.context_kernel.get("sourceHealth", {}) or {}

                if source_health:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    
                    qdrant = source_health.get('qdrant', {})
                    graph = source_health.get('graph', {})
                    bridge = source_health.get('bridge', {})
                    sqlite = source_health.get('sqlite', {})
                    
                    if qdrant.get('pointsCount') is not None:
                        detail_box.append(_build_detail_row("Qdrant", f"{qdrant['pointsCount']} points", "🗄️"))
                    if graph.get('nodesCount') is not None:
                        detail_box.append(_build_detail_row("Graph", f"{graph['nodesCount']} nodes / {graph.get('edgesCount', '?')} edges", "🕸️"))
                    if sqlite.get('status'):
                        sqlite_bits = [str(sqlite.get('status'))]
                        if sqlite.get('pendingCount') is not None:
                            sqlite_bits.append(f"pending {sqlite.get('pendingCount')}")
                        if sqlite.get('approvedCount') is not None:
                            sqlite_bits.append(f"approved {sqlite.get('approvedCount')}")
                        if sqlite.get('promotedCount') is not None:
                            sqlite_bits.append(f"promoted {sqlite.get('promotedCount')}")
                        detail_box.append(_build_detail_row("SQLite", " • ".join(sqlite_bits), "🧷"))
                    if bridge.get('status'):
                        detail_box.append(_build_detail_row("Bridge", bridge['status'], "🔗"))
                    if bridge.get('latency_ms'):
                        detail_box.append(_build_detail_row("Latency", f"{bridge['latency_ms']}ms", "⏱️"))
                
                # Section: ORICO
                if message.orico_counts:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    
                    safe = message.orico_counts.get('safeProvisional', 0)
                    review = message.orico_counts.get('ownerReview', 0)
                    privacy = message.orico_counts.get('privacyQuarantine', 0)
                    detail_box.append(_build_detail_row("Safe", str(safe), "🟢"))
                    detail_box.append(_build_detail_row("Review", str(review), "🟡"))
                    detail_box.append(_build_detail_row("Privacy", str(privacy), "🔴"))
                
                # Section: Token Budget
                if message.token_budget:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    
                    max_tok = message.token_budget.get('maxPromptTokens', '?')
                    est_tok = message.token_budget.get('estimatedPromptTokens', '?')
                    turns = message.token_budget.get('recentTurnsInjected', '?')
                    receipt_refs = message.token_budget.get('receiptRefs', [])
                    retrieval_refs = message.token_budget.get('retrievalRefs', [])
                    detail_box.append(_build_detail_row("Max", str(max_tok), "📊"))
                    detail_box.append(_build_detail_row("Estimated", str(est_tok), "📝"))
                    detail_box.append(_build_detail_row("Turns", str(turns), "🔄"))
                    if retrieval_refs:
                        detail_box.append(_build_detail_row("Retrieval", f"{len(retrieval_refs)} refs", "🔎"))
                    if receipt_refs:
                        detail_box.append(_build_detail_row("Receipts", f"{len(receipt_refs)} refs", "🧾"))
                
                # Section: Memory Refs
                if message.memory_refs:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    
                    refs_lbl = Gtk.Label(label=f"🧩 {len(message.memory_refs)} memory refs injected:")
                    refs_lbl.add_css_class("caption")
                    refs_lbl.add_css_class("dim-label")
                    refs_lbl.set_xalign(0)
                    detail_box.append(refs_lbl)
                    
                    for i, ref in enumerate(message.memory_refs[:8], 1):
                        ref_label = _display_text(ref)
                        ref_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                        ref_row.set_margin_start(16)
                        num = Gtk.Label(label=f"{i}.")
                        num.add_css_class("caption")
                        num.add_css_class("dim-label")
                        num.set_size_request(20, -1)
                        ref_row.append(num)
                        ref_txt = Gtk.Label(label=ref_label[:80] + ("…" if len(ref_label) > 80 else ""))
                        ref_txt.add_css_class("caption")
                        ref_txt.set_xalign(0)
                        ref_txt.set_selectable(True)
                        ref_txt.set_wrap(True)
                        ref_txt.set_max_width_chars(50)
                        ref_row.append(ref_txt)
                        detail_box.append(ref_row)
                    
                    if len(message.memory_refs) > 8:
                        more = Gtk.Label(label=f"  … and {len(message.memory_refs) - 8} more")
                        more.add_css_class("caption")
                        more.add_css_class("dim-label")
                        more.set_margin_start(16)
                        detail_box.append(more)
                
                # Section: Degraded / Bypass
                if message.degraded_reasons:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    
                    for reason in message.degraded_reasons:
                        detail_box.append(_build_detail_row("Warning", reason, "⚠️", warning=True))
                
                if message.harness_bypassed:
                    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
                    sep.set_margin_top(4)
                    sep.set_margin_bottom(4)
                    detail_box.append(sep)
                    detail_box.append(_build_detail_row("Status", "Harness bypassed — generic model response", "🚨", warning=True))
                
                # Toggle handler
                def _on_evidence_toggle(btn, rev):
                    active = not rev.get_reveal_child()
                    rev.set_reveal_child(active)
                    btn.set_label("🔼" if active else "🔍")
                    btn.set_tooltip_text("Collapse details" if active else "Expand Context Inspector details")
                
                expand_btn.connect("clicked", _on_evidence_toggle, revealer)
                row_click = Gtk.GestureClick()
                row_click.connect(
                    "released",
                    lambda gesture, n_press, x, y: _on_evidence_toggle(expand_btn, revealer),
                )
                toggle_row.add_controller(row_click)


class TalkColumn(Gtk.Box):
    """Center column: Roxy Conversation using local Ollama."""
    
    def __init__(self):
        print("[TalkColumn] ========== INIT BEGIN ==========" )
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("talk-column")
        self.set_hexpand(True)
        print("[TalkColumn] Base widget initialized")
        
        self._draft_mode = True  # Human-in-the-loop default
        self._speak_mode = False  # Option B: speak button, not auto-speak
        self._is_typing = False
        
        # Operator controls (Chief's Truth Panel)
        self._routing_mode = "AUTO"  # CHAT, RAG, EXEC, AUTO
        self._pool_mode = "AUTO"  # AUTO, ROXY
        self._last_factory_truth: Dict[str, Any] = {}
        self._last_factory_routes: Dict[str, Any] = {}
        
        # Services
        print("[TalkColumn] Getting services...")
        self._chat_service = get_chat_service()
        self._voice_service = get_voice_service()
        print("[TalkColumn] Services acquired")
        
        # UI references
        self._status_chip: Optional[Gtk.Label] = None
        self._model_chip: Optional[Gtk.Label] = None
        self._latency_chip: Optional[Gtk.Label] = None
        self._typing_indicator: Optional[Gtk.Box] = None
        self._status_label: Optional[Gtk.Label] = None
        self._status_spinner: Optional[Gtk.Spinner] = None
        
        # Truth Panel chips (from local Ollama status)
        self._time_chip: Optional[Gtk.Label] = None
        self._git_chip: Optional[Gtk.Label] = None
        self._ollama_chip: Optional[Gtk.Label] = None
        self._github_chip: Optional[Gtk.Label] = None
        self._info_poll_id: Optional[int] = None
        
        # Per-message meta display
        self._last_meta_chip: Optional[Gtk.Label] = None
        
        print("[TalkColumn] Building UI...")
        self._build_ui()
        print("[TalkColumn] Loading settings...")
        self._load_settings()  # Sticky settings (Phase 2C)
        print("[TalkColumn] Connecting to roxy...")
        self._connect_to_roxy()
        print("[TalkColumn] Starting info polling...")
        self._start_info_polling()
        print("[TalkColumn] Starting lane health polling...")
        self._start_lane_health_polling()
        
        print("[TalkColumn] ========== INIT COMPLETE ==========" )
    
    def _save_settings(self):
        """Persist sticky settings to JSON."""
        from pathlib import Path
        import json
        try:
            settings_dir = Path.home() / ".config" / "roxy-command-center"
            settings_dir.mkdir(parents=True, exist_ok=True)
            settings_file = settings_dir / "settings.json"
            
            data = {}
            if settings_file.exists():
                try:
                    data = json.loads(settings_file.read_text())
                except:
                    pass
            
            # Update values
            routes = ["AUTO", "CHAT", "RAG", "EXEC"]
            if hasattr(self, '_route_dropdown'):
                idx_route = self._route_dropdown.get_selected()
                if idx_route < len(routes):
                    data["route_mode"] = routes[idx_route]
            
            pools = ["AUTO", "ROXY"]
            if hasattr(self, '_pool_dropdown'):
                idx_pool = self._pool_dropdown.get_selected()
                if idx_pool < len(pools):
                    data["pool_mode"] = pools[idx_pool]
            
            # Lane selection (ROXY-COMMAND-CENTER-MODEL-LANE-SWITCHER-V1)
            lanes = ["auto", "frontier", "judge", "local", "cloud"]
            if hasattr(self, '_lane_dropdown'):
                idx_lane = self._lane_dropdown.get_selected()
                if idx_lane < len(lanes):
                    data["lane"] = lanes[idx_lane]
                
            settings_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[Talk] Failed to save settings: {e}")

    def _load_settings(self):
        """Load sticky settings."""
        from pathlib import Path
        import json
        try:
            settings_file = Path.home() / ".config" / "roxy-command-center" / "settings.json"
            if not settings_file.exists():
                return
                
            data = json.loads(settings_file.read_text())
            
            route = data.get("route_mode", "AUTO")
            routes = ["AUTO", "CHAT", "RAG", "EXEC"]
            if route in routes and hasattr(self, '_route_dropdown'):
                self._route_dropdown.set_selected(routes.index(route))
                self._routing_mode = route
                print(f"[Talk] Loaded sticky route: {route}")
            
            pool = data.get("pool_mode", "AUTO")
            pools = ["AUTO", "ROXY"]
            if pool in pools and hasattr(self, '_pool_dropdown'):
                self._pool_dropdown.set_selected(pools.index(pool))
                self._pool_mode = pool
                print(f"[Talk] Loaded sticky pool: {pool}")
            
            # Lane selection (ROXY-COMMAND-CENTER-MODEL-LANE-SWITCHER-V1)
            lane = data.get("lane", "auto")
            lanes = ["auto", "frontier", "judge", "local", "cloud"]
            lane_names = ["Auto", "Frontier Coder", "Judge", "Local Utility", "Cloud/API"]
            if lane in lanes and hasattr(self, '_lane_dropdown'):
                self._lane_dropdown.set_selected(lanes.index(lane))
                self._chat_service.set_lane(lane)
                name = lane_names[lanes.index(lane)]
                if self._current_lane_label:
                    self._current_lane_label.set_label(f"Using: {name}")
                print(f"[Talk] Loaded sticky lane: {lane}")
                
        except Exception as e:
            print(f"[Talk] Failed to load settings: {e}")

    def _build_ui(self):
        # Header with context chips
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        self.append(header)
        
        # Title row
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.append(title_row)
        
        title = Gtk.Label(label="Roxy")
        title.add_css_class("title-2")
        title.set_xalign(0)
        title_row.append(title)
        
        # Connection button
        connect_btn = Gtk.Button(label="Connect")
        connect_btn.add_css_class("suggested-action")
        connect_btn.add_css_class("pill")
        connect_btn.connect("clicked", self._on_connect_click)
        title_row.append(connect_btn)
        
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        title_row.append(spacer)
        
        # Context chips row - live local runtime data
        chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        chips_box.set_margin_bottom(8)
        header.append(chips_box)
        
        # Status chip
        self._status_chip = Gtk.Label(label="⚪ Disconnected")
        self._status_chip.add_css_class("dim-label")
        self._status_chip.add_css_class("caption")
        self._status_chip.set_tooltip_text("Connection status")
        self._status_chip.set_xalign(0)
        self._status_chip.set_width_chars(20)
        chips_box.append(self._status_chip)
        
        # Model chip
        self._model_chip = Gtk.Label(label="🧠 --")
        self._model_chip.add_css_class("dim-label")
        self._model_chip.add_css_class("caption")
        self._model_chip.set_tooltip_text("Current model")
        self._model_chip.set_xalign(0)
        self._model_chip.set_width_chars(18)
        chips_box.append(self._model_chip)
        
        # Latency chip
        self._latency_chip = Gtk.Label(label="⏱️ --")
        self._latency_chip.add_css_class("dim-label")
        self._latency_chip.add_css_class("caption")
        self._latency_chip.set_tooltip_text("Response latency")
        self._latency_chip.set_xalign(0)
        self._latency_chip.set_width_chars(14)
        chips_box.append(self._latency_chip)
        
        # Identity chip
        identity_chip = Gtk.Label(label="🎵 MindSong")
        identity_chip.add_css_class("dim-label")
        identity_chip.add_css_class("caption")
        identity_chip.set_tooltip_text("Active project context")
        chips_box.append(identity_chip)

        # Truth Panel row - authoritative server data from /info
        truth_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        truth_box.set_margin_bottom(4)
        header.append(truth_box)
        
        # Server time chip
        self._time_chip = Gtk.Label(label="🕐 --:--")
        self._time_chip.add_css_class("dim-label")
        self._time_chip.add_css_class("caption")
        self._time_chip.set_tooltip_text("Server time")
        self._time_chip.set_xalign(0)
        self._time_chip.set_width_chars(18)  # Fixed width to prevent layout thrash
        truth_box.append(self._time_chip)
        
        # Git state chip
        self._git_chip = Gtk.Label(label="🔀 --")
        self._git_chip.add_css_class("dim-label")
        self._git_chip.add_css_class("caption")
        self._git_chip.set_tooltip_text("Git branch & commit")
        self._git_chip.set_xalign(0)
        self._git_chip.set_width_chars(22)  # Fixed width to prevent layout thrash
        truth_box.append(self._git_chip)
        
        # Ollama status chip
        self._ollama_chip = Gtk.Label(label="🦙 --")
        self._ollama_chip.add_css_class("dim-label")
        self._ollama_chip.add_css_class("caption")
        self._ollama_chip.set_tooltip_text("Ollama connection")
        self._ollama_chip.set_xalign(0)
        self._ollama_chip.set_width_chars(22)  # Fixed width to prevent layout thrash
        truth_box.append(self._ollama_chip)
        
        # GitHub status chip
        self._github_chip = Gtk.Label(label="🐙 --")
        self._github_chip.add_css_class("dim-label")
        self._github_chip.add_css_class("caption")
        self._github_chip.set_tooltip_text("GitHub API status")
        self._github_chip.set_xalign(0)
        self._github_chip.set_width_chars(10)  # Fixed width to prevent layout thrash
        truth_box.append(self._github_chip)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.set_margin_bottom(4)
        header.append(status_box)

        self._status_spinner = Gtk.Spinner()
        self._status_spinner.set_visible(False)
        status_box.append(self._status_spinner)

        self._status_label = Gtk.Label(label="Connect to Roxy to begin.")
        self._status_label.set_xalign(0)
        self._status_label.set_wrap(True)
        self._status_label.add_css_class("dim-label")
        status_box.append(self._status_label)
        
        # Chat transcript
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled)
        
        self.chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scrolled.set_child(self.chat_box)
        self._chat_scrolled = scrolled  # Reference for auto-scroll
        
        # Typing indicator (hidden by default)
        self._typing_indicator = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._typing_indicator.set_margin_start(12)
        self._typing_indicator.set_margin_bottom(8)
        self._typing_indicator.set_visible(False)
        self.append(self._typing_indicator)
        
        typing_spinner = Gtk.Spinner()
        typing_spinner.start()
        self._typing_indicator.append(typing_spinner)
        
        typing_label = Gtk.Label(label="Roxy is thinking...")
        typing_label.add_css_class("dim-label")
        self._typing_indicator.append(typing_label)
        
        # Input area
        input_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        input_area.set_margin_start(12)
        input_area.set_margin_end(12)
        input_area.set_margin_bottom(12)
        self.append(input_area)

        # Factory truth strip: one compact source of route/status truth above input.
        factory_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        factory_row.set_margin_bottom(6)
        input_area.append(factory_row)

        self._factory_badge = TruthBadge("Factory", "UNPROVEN")
        factory_row.append(self._factory_badge)

        self._route_truth_badges = TruthBadgeGroup(spacing=6)
        for key, label_text in [
            ("chat_proxy", "Proxy"),
            ("litellm", "LiteLLM"),
            ("frontier", "Ada"),
            ("decode_6900xt", "6900XT"),
            ("judge_235b", "Judge"),
        ]:
            self._route_truth_badges.set_badge(key, label_text, "LOADING")
        factory_row.append(self._route_truth_badges)
        
        # Mode toggle row
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_area.append(mode_box)
        
        mode_label = Gtk.Label(label="Mode:")
        mode_label.add_css_class("dim-label")
        mode_box.append(mode_label)
        
        self.draft_btn = Gtk.ToggleButton(label="Draft")
        self.draft_btn.set_active(True)
        self.draft_btn.set_tooltip_text("Roxy drafts, you approve (safe)")
        self.draft_btn.connect("toggled", self._on_mode_toggle, True)
        mode_box.append(self.draft_btn)
        
        self.send_btn = Gtk.ToggleButton(label="Send")
        self.send_btn.set_tooltip_text("Roxy sends directly (requires explicit arming)")
        self.send_btn.connect("toggled", self._on_mode_toggle, False)
        mode_box.append(self.send_btn)
        
        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        mode_box.append(spacer)
        
        # Speak toggle (Option B: manual button)
        self.speak_btn = Gtk.ToggleButton()
        self.speak_btn.set_icon_name("audio-speakers-symbolic")
        self.speak_btn.set_tooltip_text("Toggle voice output (Option B)")
        self.speak_btn.connect("toggled", self._on_speak_toggle)
        mode_box.append(self.speak_btn)
        
        # === OPERATOR CONTROLS ROW (Chief's Truth Panel) ===
        operator_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_area.append(operator_box)
        
        # Routing Mode: CHAT/RAG/EXEC/AUTO
        route_label = Gtk.Label(label="Route:")
        route_label.add_css_class("dim-label")
        operator_box.append(route_label)
        
        self._route_dropdown = Gtk.DropDown.new_from_strings(["AUTO", "CHAT", "RAG", "EXEC"])
        self._route_dropdown.set_selected(0)  # AUTO by default
        self._route_dropdown.set_tooltip_text("AUTO=smart routing, CHAT=direct LLM, RAG=retrieval, EXEC=strict")
        self._route_dropdown.connect("notify::selected", self._on_route_changed)
        operator_box.append(self._route_dropdown)
        
        # Pool: current ROXY has one Ollama runtime.
        pool_label = Gtk.Label(label="Pool:")
        pool_label.add_css_class("dim-label")
        pool_label.set_margin_start(12)
        operator_box.append(pool_label)

        self._pool_dropdown = Gtk.DropDown.new_from_strings(["AUTO", "ROXY"])
        self._pool_dropdown.set_selected(0)  # AUTO by default
        self._pool_dropdown.set_tooltip_text("AUTO=ROXY harness :4001 → LiteLLM :4000 → Qwen MTP :8085")
        self._pool_dropdown.connect("notify::selected", self._on_pool_changed)
        operator_box.append(self._pool_dropdown)
        
        # Spacer
        op_spacer = Gtk.Box()
        op_spacer.set_hexpand(True)
        operator_box.append(op_spacer)
        
        # Last execution meta chip (updates after each message)
        self._last_meta_chip = Gtk.Label(label="")
        self._last_meta_chip.add_css_class("dim-label")
        self._last_meta_chip.add_css_class("caption")
        self._last_meta_chip.set_tooltip_text("Last request execution details")
        operator_box.append(self._last_meta_chip)
        
        # === LANE SELECTOR (ROXY-COMMAND-CENTER-MODEL-LANE-SWITCHER-V1) ===
        lane_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lane_box.set_margin_top(4)
        lane_box.set_margin_bottom(4)
        input_area.append(lane_box)
        
        lane_label = Gtk.Label(label="Lane:")
        lane_label.add_css_class("dim-label")
        lane_box.append(lane_label)
        
        self._lane_dropdown = Gtk.DropDown.new_from_strings([
            "Auto", "Frontier Coder", "Judge", "Local Utility", "Cloud/API"
        ])
        self._lane_dropdown.set_selected(0)  # Auto
        cloud_tip = "Cloud=Claude fallback (requires ANTHROPIC_API_KEY)" if os.environ.get("ANTHROPIC_API_KEY") else "Cloud=Claude fallback 🔒 ANTHROPIC_API_KEY not set"
        self._lane_dropdown.set_tooltip_text(
            f"Auto=smart routing | Frontier=Qwen3.6-27B Ada :8085 | "
            f"Judge=Qwen3-235B CPU :8084 | Local=Ollama 7B :11434 | {cloud_tip}"
        )
        self._lane_dropdown.connect("notify::selected", self._on_lane_changed)
        lane_box.append(self._lane_dropdown)
        
        # Active route truth label (updated from last response)
        self._current_lane_label = Gtk.Label(label="Using: Auto")
        self._current_lane_label.add_css_class("dim-label")
        self._current_lane_label.add_css_class("caption")
        self._current_lane_label.set_margin_start(8)
        lane_box.append(self._current_lane_label)
        
        # Spacer
        lane_spacer = Gtk.Box()
        lane_spacer.set_hexpand(True)
        lane_box.append(lane_spacer)
        
        # Phase 4: Save-authority toolbar
        save_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        save_toolbar.set_margin_top(4)
        input_area.append(save_toolbar)
        
        save_btn = Gtk.Button(label="💾 Save")
        save_btn.add_css_class("flat")
        save_btn.add_css_class("caption")
        save_btn.set_tooltip_text("Save conversation to session file")
        save_btn.connect("clicked", self._on_save_session)
        save_toolbar.append(save_btn)
        
        export_btn = Gtk.Button(label="📤 Export")
        export_btn.add_css_class("flat")
        export_btn.add_css_class("caption")
        export_btn.set_tooltip_text("Export conversation to markdown file")
        export_btn.connect("clicked", self._on_export_session)
        save_toolbar.append(export_btn)
        
        clear_btn = Gtk.Button(label="🗑️ Clear")
        clear_btn.add_css_class("flat")
        clear_btn.add_css_class("caption")
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_tooltip_text("Clear conversation history (requires confirmation)")
        clear_btn.connect("clicked", self._on_clear_session)
        save_toolbar.append(clear_btn)
        
        self._save_status_label = Gtk.Label(label="")
        self._save_status_label.add_css_class("caption")
        self._save_status_label.add_css_class("dim-label")
        self._save_status_label.set_margin_start(8)
        save_toolbar.append(self._save_status_label)
        
        # Input row
        input_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_area.append(input_row)
        
        # Voice button (push-to-talk)
        voice_btn = Gtk.Button()
        voice_btn.set_icon_name("audio-input-microphone-symbolic")
        voice_btn.set_tooltip_text("Push to talk (Phase 2)")
        voice_btn.add_css_class("circular")
        voice_btn.connect("clicked", self._on_voice_click)
        input_row.append(voice_btn)
        
        # Keep Send visible even when the right operator pane is narrow.
        self._send_action_btn = Gtk.Button(label="Send")
        self._send_action_btn.add_css_class("suggested-action")
        self._send_action_btn.set_size_request(64, -1)
        self._send_action_btn.connect("clicked", self._on_send)
        input_row.append(self._send_action_btn)

        # Text entry
        self.entry = Gtk.Entry()
        self.entry.set_hexpand(True)
        self.entry.set_placeholder_text("Talk to Roxy...")
        self.entry.connect("activate", self._on_send)

        # Phase 7: Keyboard shortcuts — Ctrl+Enter to send, Escape to clear
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_entry_key_pressed)
        self.entry.add_controller(key_controller)

        input_row.append(self.entry)

        # Make the chat surface immediately usable without hunting for the entry.
        GLib.idle_add(self._focus_chat_entry)

    def _focus_chat_entry(self):
        """Move keyboard focus into the Roxy input field."""
        try:
            if hasattr(self, "entry") and self.entry:
                self.entry.grab_focus()
        except Exception as exc:
            print(f"[Talk] Could not focus chat entry: {exc}")
        return False
    
    def _connect_to_roxy(self):
        """Connect to local Ollama via ChatService."""
        self._chat_service.connect(
            identity=ServiceIdentity.MINDSONG,
            on_message=self._on_chat_message,
            on_status_change=self._on_status_change,
            on_typing=self._on_typing_change,
            on_meta_update=self._on_meta_update
        )

    def _on_meta_update(self, meta: dict):
        """Update the last execution metadata chip."""
        if not self._last_meta_chip:
            return
            
        # Format: [MODE:POOL] route -> model (t ms)
        mode = (meta.get("mode") or "??").upper()
        pool = (meta.get("pool") or "AUTO").upper()
        route = meta.get("route") or "?"
        model = meta.get("model_used")
        if model:
            # Shorten model name
            model = model.replace("qwen2.5-coder:14b", "Qwen14B").replace("llama3.1:8b", "L3.8B").split(":")[0]
        
        total_ms = meta.get("total_ms")
        timing = f"{total_ms}ms" if total_ms else ""
        
        text = f"[{mode}:{pool}] {route}"
        if model:
            text += f" → {model}"
        if timing:
            text += f" ({timing})"
            
        # Update chip
        self._last_meta_chip.set_label(text)
        
        # Tooltip with full details
        full_text = "\n".join([f"{k}: {v}" for k, v in meta.items()])
        self._last_meta_chip.set_tooltip_text(f"Last Execution:\n{full_text}")
    
    def _start_info_polling(self):
        """Take one local status snapshot; no background polling in review build."""
        self._info_fetch_pending = False  # Guard against concurrent fetches
        GLib.idle_add(self._poll_info)
    
    def _poll_info(self) -> bool:
        """Fetch ROXY harness health and update Truth Panel chips."""
        # Skip if previous fetch still in progress (prevents thread accumulation)
        if getattr(self, '_info_fetch_pending', False):
            return True

        self._info_fetch_pending = True

        import threading
        def fetch():
            try:
                import urllib.request
                import json
                # Canonical: check ROXY harness :4001/health
                req = urllib.request.Request("http://127.0.0.1:4001/health")
                req.add_header("User-Agent", "roxy-command-center/truth-panel")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    payload = json.loads(resp.read().decode())
                    data = {
                        "server_time_iso": datetime.now().isoformat(),
                        "harness": payload,
                    }
                    GLib.idle_add(self._update_truth_panel, data)
            except Exception as e:
                GLib.idle_add(self._update_truth_panel_error, str(e))
            finally:
                self._info_fetch_pending = False

        threading.Thread(target=fetch, daemon=True).start()
        return False  # Manual snapshot only
    
    def _update_truth_panel(self, data: dict):
        """Update Truth Panel chips with harness /health data."""
        if self._time_chip:
            try:
                ts = data.get("server_time_iso", "")
                if ts:
                    dt = datetime.fromisoformat(ts)
                    self._time_chip.set_label(f"🕐 {dt.strftime('%Y-%m-%d %H:%M')}")
            except:
                self._time_chip.set_label("🕐 --")
        
        if self._git_chip:
            git = data.get("git", {})
            branch = git.get("branch", "?")
            sha = git.get("head_sha", "?")[:7]
            state = "⚠️" if git.get("dirty") else "✔"
            self._git_chip.set_label(f"🔀 {branch} • {sha} • {state}")
            self._git_chip.set_tooltip_text(git.get("last_commit_subject", ""))
        
        # Harness chip (was Ollama chip — now shows ROXY harness status)
        if self._ollama_chip:
            harness = data.get("harness", {})
            ok = bool(harness.get("ok"))
            upstream_ok = bool(harness.get("upstreamReachable"))
            prompt_loaded = bool(harness.get("promptLoaded"))
            skill_count = harness.get("skillEmbeddingsLoaded", 0)
            storage = harness.get("storage", {})
            storage_status = storage.get("status", "unknown")
            svc = harness.get("service", "roxy-chat-proxy")

            status_icon = "✅" if ok and upstream_ok else "⚠️" if ok else "❌"
            self._ollama_chip.set_label(
                f"🧠 {status_icon} {svc} ({storage_status})"
            )
            self._ollama_chip.set_tooltip_text(
                f"ROXY Harness: {svc}\n"
                f"Upstream: {'OK' if upstream_ok else 'DOWN'}\n"
                f"Prompt: {'loaded' if prompt_loaded else 'missing'}\n"
                f"Skills: {skill_count}\n"
                f"Store: {storage_status}\n"
                f"DB: {storage.get('dbPath', 'N/A')}"
            )

            if ok and upstream_ok:
                self._ollama_chip.remove_css_class("error")
            else:
                self._ollama_chip.add_css_class("error")
        
        if self._github_chip:
            github = data.get("github", {})
            
            # Show GitHub status: configured + reachable
            if github.get("configured"):
                status = "ok" if github.get("reachable") else "err"
                self._github_chip.set_label(f"🐙 {status}")
                
                # Tooltip with details
                tooltip_parts = []
                if github.get("latency_ms"):
                    tooltip_parts.append(f"Latency: {github['latency_ms']}ms")
                if github.get("rate_limit"):
                    rl = github["rate_limit"]
                    tooltip_parts.append(f"Rate limit: {rl.get('remaining', '?')}/{rl.get('limit', '?')}")
                if github.get("error"):
                    tooltip_parts.append(f"Error: {github['error']}")
                
                self._github_chip.set_tooltip_text("\n".join(tooltip_parts) if tooltip_parts else "GitHub API connected")
                
                # Color based on reachable
                if github.get("reachable"):
                    self._github_chip.remove_css_class("error")
                else:
                    self._github_chip.add_css_class("error")
            else:
                self._github_chip.set_label("🐙 unset")
                self._github_chip.set_tooltip_text("GitHub token not configured")
                self._github_chip.add_css_class("error")
    
    def _update_truth_panel_error(self, error: str):
        """Handle /info fetch error."""
        if self._time_chip:
            self._time_chip.set_label("🕐 --:--")
        if self._git_chip:
            self._git_chip.set_label("🔀 --")
        if self._ollama_chip:
            self._ollama_chip.set_label("🦙 ❌")
            self._ollama_chip.set_tooltip_text(f"Ollama status unavailable: {error}")
        if self._github_chip:
            self._github_chip.set_label("🐙 --")
            self._github_chip.set_tooltip_text(f"Local status unavailable: {error}")

    def _on_connect_click(self, button):
        """Manual reconnect."""
        if self._status_chip:
            self._status_chip.set_label("🟡 Connecting")
        if self._model_chip:
            self._model_chip.set_label("🧠 --")
        if self._latency_chip:
            self._latency_chip.set_label("⏱️ --")
        if self._status_label:
            self._status_label.set_label("Connecting to Roxy…")
        if self._status_spinner:
            self._status_spinner.set_visible(True)
            self._status_spinner.start()
        if self._typing_indicator:
            self._typing_indicator.set_visible(False)
        self._connect_to_roxy()
    
    def _scroll_to_bottom(self):
        """Auto-scroll chat to bottom when new messages arrive."""
        if hasattr(self, '_chat_scrolled'):
            adj = self._chat_scrolled.get_vadjustment()
            if adj:
                # Use idle_add to scroll after widget allocation
                def _do_scroll():
                    adj.set_value(adj.get_upper() - adj.get_page_size())
                    return False
                GLib.idle_add(_do_scroll)
    
    def _on_chat_message(self, message: ServiceChatMessage):
        """Called when a new message arrives (user or assistant)."""
        # Convert to UI widget with harness metadata
        ui_message = ChatMessage(
            id=message.id,
            role=message.role,
            content=message.content,
            timestamp=message.timestamp,
            latency_ms=getattr(message, 'latency_ms', 0),
            model=getattr(message, 'model', ''),
            memory_refs=getattr(message, 'memory_refs', []),
            proposed_actions=getattr(message, 'proposed_actions', []),
            context_hash=getattr(message, 'context_hash', ''),
            context_kernel_version=getattr(message, 'context_kernel_version', ''),
            context_kernel_hash=getattr(message, 'context_kernel_hash', ''),
            context_kernel=getattr(message, 'context_kernel', {}),
            source_health=getattr(message, 'source_health', {}),
            token_budget=getattr(message, 'token_budget', {}),
            orico_counts=getattr(message, 'orico_counts', {}),
            degraded_reasons=getattr(message, 'degraded_reasons', []),
            harness_bypassed=getattr(message, 'harness_bypassed', False),
        )
        widget = ChatMessage_Widget(ui_message)
        self.chat_box.append(widget)
        
        # Add "Ask Judge" button for assistant messages (ROXY-COMMAND-CENTER-MODEL-LANE-SWITCHER-V1)
        if message.role == "assistant":
            health = self._chat_service.get_lane_health()
            judge_info = health.get("judge", {})
            # Judge is usable if status is healthy (even if slow)
            judge_alive = judge_info.get("status") == "healthy" or judge_info.get("truthGrade") == "live_probe"
            judge_tps = judge_info.get("tps")
            judge_slow = judge_tps is not None and judge_tps < 10  # Under 10 t/s = slow

            # If this response came from Judge, label it
            model_used = getattr(message, 'model', '') or ''
            is_judge_response = 'judge' in model_used.lower() or 'cpu-supermodel' in model_used.lower()

            judge_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            judge_box.set_margin_start(12)
            judge_box.set_margin_end(12)
            judge_box.set_margin_bottom(8)
            self.chat_box.append(judge_box)

            if is_judge_response:
                judge_header = Gtk.Label(label="⚖️ Judge Review")
                judge_header.add_css_class("caption")
                judge_header.add_css_class("accent")
                judge_box.append(judge_header)

            judge_btn = Gtk.Button(label="⚖️ Ask Judge")
            judge_btn.add_css_class("pill")
            judge_btn.add_css_class("caption")
            if judge_alive:
                judge_btn.add_css_class("suggested-action")
                tooltip = "Send this response to Judge for adversarial review"
                if judge_slow:
                    tooltip += " (expect 1–3 min)"
                judge_btn.set_tooltip_text(tooltip)
                judge_btn.connect("clicked", self._on_ask_judge, message.content)
            else:
                judge_btn.set_sensitive(False)
                judge_btn.set_tooltip_text("Judge lane is not available")
            judge_box.append(judge_btn)

            send_to_judge_btn = Gtk.Button(label="📤 Send plan to Judge")
            send_to_judge_btn.add_css_class("pill")
            send_to_judge_btn.add_css_class("caption")
            if judge_alive:
                tooltip = "Send current plan/response to Judge for deep review"
                if judge_slow:
                    tooltip += " (expect 1–3 min)"
                send_to_judge_btn.set_tooltip_text(tooltip)
                send_to_judge_btn.connect("clicked", self._on_ask_judge, message.content)
            else:
                send_to_judge_btn.set_sensitive(False)
                send_to_judge_btn.set_tooltip_text("Judge lane is not available")
            judge_box.append(send_to_judge_btn)
        
        self._scroll_to_bottom()
        
        # Update latency chip for assistant messages
        if message.role == "assistant":
            latency = self._chat_service.latency_ms
            self._latency_chip.set_label(f"⏱️ {latency}ms")
            
            # Speak if speak mode enabled (Option B)
            if self._speak_mode:
                self._voice_service.speak(message.content)

    def _append_system_message(self, text: str):
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role="system",
            content=text,
            timestamp=datetime.now()
        )
        widget = ChatMessage_Widget(message)
        self.chat_box.append(widget)
        self._scroll_to_bottom()
    
    def _on_status_change(self, status: ConnectionStatus, message: str):
        """Called when connection status changes."""
        status_icons = {
            ConnectionStatus.DISCONNECTED: "⚪",
            ConnectionStatus.CONNECTING: "🟡",
            ConnectionStatus.WARMING: "🟠",
            ConnectionStatus.CONNECTED: "🟢",
            ConnectionStatus.ERROR: "🔴"
        }
        icon = status_icons.get(status, "⚪")
        
        # Update chips
        if self._status_chip:
            self._status_chip.set_label(f"{icon} {status.value.title()}")

        if self._status_label:
            detail = message or status.value.title()
            self._status_label.set_label(detail)

        if self._status_spinner:
            show_spinner = status in (ConnectionStatus.CONNECTING, ConnectionStatus.WARMING)
            self._status_spinner.set_visible(show_spinner)
            if show_spinner:
                self._status_spinner.start()
            else:
                self._status_spinner.stop()

        if status == ConnectionStatus.CONNECTED:
            model = self._chat_service.model or "ready"
            if self._model_chip:
                self._model_chip.set_label(f"🧠 {model}")
        elif status == ConnectionStatus.WARMING:
            if self._model_chip:
                self._model_chip.set_label("🧠 warming…")
        elif status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR):
            if self._model_chip:
                self._model_chip.set_label("🧠 --")

        if status != ConnectionStatus.CONNECTED and self._latency_chip:
            self._latency_chip.set_label("⏱️ --")
    
    def _on_typing_change(self, is_typing: bool):
        """Called when typing indicator should show/hide."""
        self._is_typing = is_typing
        if self._typing_indicator:
            self._typing_indicator.set_visible(is_typing)
    
    def _on_mode_toggle(self, button, is_draft: bool):
        if button.get_active():
            self._draft_mode = is_draft
            if is_draft:
                self.send_btn.set_active(False)
                self._chat_service.set_mode(ChatMode.DRAFT)
            else:
                self.draft_btn.set_active(False)
                self._chat_service.set_mode(ChatMode.SEND)
                # Warn about send mode
                print("[Talk] WARNING: Send mode enabled - Roxy will execute without approval")
    
    def _on_route_changed(self, dropdown, _pspec):
        """Handle routing mode change (CHAT/RAG/EXEC/AUTO)."""
        routes = ["AUTO", "CHAT", "RAG", "EXEC"]
        idx = dropdown.get_selected()
        self._routing_mode = routes[idx] if idx < len(routes) else "AUTO"
        print(f"[Talk] Routing mode: {self._routing_mode}")
        self._save_settings()
    
    def _on_pool_changed(self, dropdown, _pspec):
        """Handle pool change (AUTO/ROXY)."""
        pools = ["AUTO", "ROXY"]
        idx = dropdown.get_selected()
        self._pool_mode = pools[idx] if idx < len(pools) else "AUTO"
        print(f"[Talk] Pool: {self._pool_mode}")
        self._save_settings()
    
    def _on_lane_changed(self, dropdown, _pspec):
        """Handle lane selection change."""
        lanes = ["auto", "frontier", "judge", "local", "cloud"]
        names = ["Auto", "Frontier Coder", "Judge", "Local Utility", "Cloud/API"]
        idx = dropdown.get_selected()
        lane = lanes[idx] if idx < len(lanes) else "auto"
        name = names[idx] if idx < len(names) else "Auto"
        self._chat_service.set_lane(lane)
        if self._current_lane_label:
            self._current_lane_label.set_label(f"Using: {name}")
        print(f"[Talk] Lane: {lane} → {self._chat_service.selected_lane}")
        self._save_settings()

        # Credential-blocked warning for Cloud
        if lane == "cloud" and not os.environ.get("ANTHROPIC_API_KEY"):
            self._append_system_message(
                "🔒 Cloud lane selected but ANTHROPIC_API_KEY is not set. "
                "Set it in your environment or choose a different lane."
            )

        # SLOW warning for Judge
        if lane == "judge":
            self._append_system_message(
                "⚠️ Judge selected: Qwen3-235B on CPU (~3.5 t/s). Responses may take 1–3 minutes."
            )
    
    def update(self, data: dict):
        """Update the Chat cockpit from daemon + factory truth snapshots."""
        factory_truth = data.get("factoryTruth") or {}
        if factory_truth:
            self._last_factory_truth = factory_truth
            self._update_factory_truth_display(factory_truth)
        factory_routes = data.get("factoryRoutes") or {}
        if factory_routes:
            self._last_factory_routes = factory_routes

    def _update_factory_truth_display(self, truth: Dict[str, Any]):
        """Render Factory status and route truth using TruthBadge components."""
        verdict = truth.get("verdict", "UNKNOWN")
        ready = truth.get("ready") or {}
        services = truth.get("servicesById") or {}
        receipt = truth.get("receiptPath") or ""
        generated_at = truth.get("generatedAt")
        stale = truth.get("stale", False)
        stale_reason = truth.get("staleReason")
        command_id = truth.get("commandId", "factory.status")
        warnings = truth.get("warnings") or []
        errors = truth.get("errors") or []

        provenance = {
            "source": "rcc",
            "command": command_id,
            "timestamp": generated_at,
            "receiptPath": receipt,
            "stale": stale,
        }

        detail_parts = []
        if stale:
            detail_parts.append(f"STALE: {stale_reason or 'refresh failed'}")
        if warnings:
            detail_parts.append("; ".join(warnings[:2]))
        if errors:
            detail_parts.append("; ".join(errors[:2]))

        if hasattr(self, "_factory_badge") and self._factory_badge:
            self._factory_badge.set_truth(
                verdict,
                provenance,
                detail="; ".join(detail_parts) if detail_parts else ""
            )

        badge_group = getattr(self, "_route_truth_badges", None)
        if badge_group:
            route_map = {
                "chat_proxy": ("Proxy", "chatProxy"),
                "litellm": ("LiteLLM", "litellm"),
                "frontier": ("Ada", "qwenMtp"),
                "decode_6900xt": ("6900XT", "decode6900xt"),
                "judge_235b": ("Judge", "judge"),
            }
            for key, (label, ready_key) in route_map.items():
                svc = services.get(key, {}) if isinstance(services, dict) else {}
                is_ready = bool(svc.get("ready")) or bool(ready.get(ready_key))
                port = svc.get("port", "")
                status = svc.get("status", "unknown")
                detail = f"port {port}, status {status}" if port else f"status {status}"
                if stale:
                    detail += " (stale)"
                badge_group.set_badge(
                    key,
                    label,
                    "PASS" if is_ready else "FAIL",
                    provenance,
                    detail=detail,
                )

    def _on_ask_judge(self, button, text: str):
        """Send current message/plan to Judge lane for adversarial review."""
        print(f"[Talk] Asking Judge to review: {text[:60]}...")
        self._chat_service.ask_judge(
            f"Please perform an adversarial review of the following:\n\n{text}\n\n"
            "Identify any errors, assumptions, gaps, or quality issues."
        )
    
    def _on_speak_toggle(self, button):
        """Toggle speak mode (Option B)."""
        self._speak_mode = button.get_active()
        self._voice_service.speak_mode = self._speak_mode
        if self._speak_mode:
            print("[Talk] Speak mode ON - responses will be spoken")
        else:
            print("[Talk] Speak mode OFF")
    
    def _on_voice_click(self, button):
        """Voice button - push-to-talk (Phase 2 stub)."""
        print("[Talk] Voice input not yet implemented (Phase 2)")
        # In Phase 2: self._voice_service.start_recording()
    
    def _on_save_session(self, button):
        """Manually trigger session save."""
        if self._chat_service.save_session():
            self._save_status_label.set_label("💾 Saved")
        else:
            self._save_status_label.set_label("❌ Save failed")
        GLib.timeout_add_seconds(3, lambda: self._save_status_label.set_label("") or False)
    
    def _on_export_session(self, button):
        """Export conversation to markdown."""
        path = self._chat_service.export_to_markdown()
        if path:
            self._save_status_label.set_label(f"📤 {path.name}")
        else:
            self._save_status_label.set_label("❌ Export failed")
        GLib.timeout_add_seconds(5, lambda: self._save_status_label.set_label("") or False)
    
    def _on_clear_session(self, button):
        """Clear conversation with confirmation dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Clear conversation history?",
        )
        dialog.set_secondary_text("This will erase all messages and reset the session. This action cannot be undone.")
        
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                if self._chat_service.clear_session():
                    # Clear UI
                    child = self.chat_box.get_first_child()
                    while child:
                        next_child = child.get_next_sibling()
                        self.chat_box.remove(child)
                        child = next_child
                    self._append_system_message("🗑️ Conversation cleared. Session reset.")
                    self._save_status_label.set_label("🗑️ Cleared")
                else:
                    self._save_status_label.set_label("❌ Clear failed")
                GLib.timeout_add_seconds(3, lambda: self._save_status_label.set_label("") or False)
            dialog.destroy()
        
        dialog.connect("response", on_response)
        dialog.show()
    
    def _detect_natural_language_intent(self, text: str) -> str:
        """Detect routing intent from natural language. Returns CHAT/RAG/EXEC/""."""
        t = text.lower().strip()
        
        # EXEC patterns: run commands, execute scripts, start/stop services
        exec_patterns = [
            r"\b(run|execute|exec|start|stop|restart|kill)\b.*\b(script|service|command|backup|deploy|build|test)",
            r"\b(back me up|do a backup|deploy|run the|execute the)\b",
            r"\b(show|list|get)\b.*\b(status|logs|processes|services)\b",
        ]
        import re
        for p in exec_patterns:
            if re.search(p, t, re.IGNORECASE):
                return "EXEC"
        
        # RAG patterns: memory retrieval, knowledge queries
        rag_patterns = [
            r"\b(what do you remember|what do you know|what do we know)\b",
            r"\b(what happened|tell me about|explain|summarize|search for|find|look up)\b.*\b(in the last|about|regarding|on|corpus|ORICO|document|file|dataset)\b",
            r"\b(look up|retrieve|query|search)\b",
            r"\b(ORICO|corpus|training|dataset|document|file)\b",
            r"\b(what|where|how|when|why|who|status|count|info)\b.*\b(ORICO|corpus|training|dataset|document|file)\b",
            r"\b(supervillain check|system status|health check|audit)\b",
        ]
        for p in rag_patterns:
            if re.search(p, t, re.IGNORECASE):
                return "RAG"
        
        # CHAT patterns: direct conversation, no retrieval needed
        chat_patterns = [
            r"^(hi|hello|hey|howdy|greetings)\b",
            r"\b(how are you|what's up|how's it going|good morning|good evening)\b",
            r"\b(thank you|thanks|please|sorry)\b",
            r"^(yes|no|maybe|ok|sure|got it|understood)$",
        ]
        for p in chat_patterns:
            if re.search(p, t, re.IGNORECASE):
                return "CHAT"
        
        return ""
    
    def _on_entry_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard shortcuts in the entry field."""
        from gi.repository import Gdk
        ctrl = (state & Gdk.ModifierType.CONTROL_MASK) != 0
        
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # Enter sends from the operator prompt; Ctrl+Enter remains supported.
            self._on_send(self.entry)
            return True
        elif keyval == Gdk.KEY_Escape:
            # Escape clears entry (if not empty) or defocuses
            text = self.entry.get_text().strip()
            if text:
                self.entry.set_text("")
            else:
                self.entry.set_can_focus(False)
                self.entry.set_can_focus(True)
            return True
        return False
    
    def _on_send(self, widget):
        """Send message to local Ollama."""
        text = self.entry.get_text().strip()
        if not text:
            return
        
        status = self._chat_service.status
        if status in (ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR):
            if self._status_label:
                self._status_label.set_label("Not connected. Click Connect.")
            self._append_system_message("⚠️ Not connected. Click Connect to retry.")
            return

        self.entry.set_text("")
        
        # Phase 3: Natural language routing — detect intent when in AUTO mode
        detected_route = ""
        effective_route = self._routing_mode
        if self._routing_mode == "AUTO":
            detected_route = self._detect_natural_language_intent(text)
            if detected_route:
                effective_route = detected_route
                # Briefly flash the detected route in status
                if self._status_label:
                    self._status_label.set_label(f"🔀 AUTO → {detected_route}")
                    # Reset after 3 seconds
                    def _reset_status():
                        if self._status_label:
                            self._status_label.set_label("Ready")
                        return False
                    GLib.timeout_add_seconds(3, _reset_status)
        
        # Pass operator controls to chat service (Chief's Truth Panel)
        self._chat_service.send_message(
            text, 
            routing_mode=effective_route if effective_route != "AUTO" else "",
            pool=self._pool_mode if self._pool_mode != "AUTO" else ""
        )


class ExecutionRunCard(Gtk.Box):
    """Compact operational row for an execution run."""
    
    def __init__(self, run: ExecutionRun):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.run = run
        self.add_css_class("progression-row")
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_bottom(4)
        self.set_margin_top(2)
        
        # Status icon
        status_icons = {
            RunStatus.QUEUED: "content-loading-symbolic",
            RunStatus.RUNNING: "emblem-synchronizing-symbolic",
            RunStatus.COMPLETED: "emblem-ok-symbolic",
            RunStatus.FAILED: "dialog-error-symbolic",
            RunStatus.CANCELLED: "process-stop-symbolic",
        }
        icon = Gtk.Image.new_from_icon_name(status_icons.get(run.status, "emblem-default-symbolic"))
        icon.set_pixel_size(16)
        if run.status == RunStatus.COMPLETED:
            icon.add_css_class("success")
        elif run.status == RunStatus.FAILED:
            icon.add_css_class("error")
        elif run.status == RunStatus.RUNNING:
            icon.add_css_class("accent")
        self.append(icon)
        
        # Name
        name_label = Gtk.Label(label=run.name)
        name_label.set_xalign(0)
        name_label.set_hexpand(True)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.add_css_class("caption")
        self.append(name_label)
        
        pct = run.progress_pct if run.progress_pct is not None else 0
        pct_label = Gtk.Label(label=f"{pct}%")
        pct_label.add_css_class("caption")
        pct_label.add_css_class("monospace")
        pct_label.set_width_chars(4)
        self.append(pct_label)

        age_label = Gtk.Label(label=self._format_age(run.started_at))
        age_label.add_css_class("caption")
        age_label.add_css_class("dim-label")
        age_label.set_width_chars(7)
        self.append(age_label)

        status_text = "FAILED" if run.status == RunStatus.FAILED else run.status.value.upper()
        status_label = Gtk.Label(label=status_text)
        status_label.add_css_class("caption")
        status_label.add_css_class("dim-label")
        status_label.set_width_chars(9)
        self.append(status_label)
        
        if run.status == RunStatus.QUEUED:
            run_btn = Gtk.Button(label="▶")
            run_btn.add_css_class("suggested-action")
            run_btn.set_tooltip_text("Run")
            run_btn.connect("clicked", self._on_dispatch)
            self.append(run_btn)
        
        if run.status == RunStatus.RUNNING and run.can_cancel:
            cancel_btn = Gtk.Button(label="■")
            cancel_btn.add_css_class("destructive-action")
            cancel_btn.set_tooltip_text("Cancel")
            cancel_btn.connect("clicked", self._on_cancel)
            self.append(cancel_btn)
        
        logs_btn = Gtk.Button(label="Logs")
        logs_btn.add_css_class("flat")
        logs_btn.add_css_class("caption")
        logs_btn.connect("clicked", self._on_logs)
        self.append(logs_btn)

    def _format_age(self, started_at) -> str:
        if not started_at:
            return "--"
        try:
            if isinstance(started_at, str):
                started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            else:
                started = started_at
            now = datetime.now(started.tzinfo) if started.tzinfo else datetime.now()
            seconds = max(0, int((now - started).total_seconds()))
            if seconds < 60:
                return f"{seconds}s"
            if seconds < 3600:
                return f"{seconds // 60}m"
            return f"{seconds // 3600}h"
        except Exception:
            return "--"
    
    def _on_dispatch(self, button):
        """Dispatch run - TODO: call POST /api/runs/:id/dispatch."""
        print(f"[Execute] Dispatching run {self.run.id}")
    
    def _on_cancel(self, button):
        """Cancel run - TODO: call POST /api/runs/:id/cancel."""
        print(f"[Execute] Cancelling run {self.run.id}")
    
    def _on_logs(self, button):
        """Show logs - TODO: navigate to logs view."""
        print(f"[Execute] Opening logs for {self.run.id}")


class ExecuteColumn(Gtk.Box):
    """Right column: Progressions / Execution Timeline."""
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("execute-column")
        self.set_size_request(300, -1)
        
        self._runs: List[ExecutionRun] = []
        
        self._build_ui()
        self._load_data()
    
    def _build_ui(self):
        # ── Safety Rail (Live System) ──
        self.safety_rail = OperatorSafetyRail()
        self.append(self.safety_rail)

        # ── Progressions header ──
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(12)
        header.set_margin_start(12)
        header.set_margin_end(12)
        header.set_margin_bottom(8)
        self.append(header)

        title = Gtk.Label(label="Progressions")
        title.add_css_class("title-2")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)

        refresh_btn = Gtk.Button()
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.add_css_class("flat")
        refresh_btn.set_tooltip_text("Refresh from canonical sources")
        refresh_btn.connect("clicked", self._on_refresh)
        header.append(refresh_btn)

        # ── Runs list ──
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(scrolled)

        self.runs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scrolled.set_child(self.runs_box)

        # ── Quick actions footer ──
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_start(12)
        footer.set_margin_end(12)
        footer.set_margin_bottom(12)
        self.append(footer)

        all_logs_btn = Gtk.Button(label="Open All Logs")
        all_logs_btn.add_css_class("flat")
        footer.append(all_logs_btn)
    
    def update(self, data: dict):
        """Update safety rail from daemon data."""
        if hasattr(self, "safety_rail"):
            self.safety_rail.update(data)

    def _load_data(self):
        """Load execution runs from canonical sources."""
        raw_runs = OrchestratorTruthProvider.get_runs()
        status_map = {
            "queued": RunStatus.QUEUED,
            "running": RunStatus.RUNNING,
            "completed": RunStatus.COMPLETED,
            "failed": RunStatus.FAILED,
            "cancelled": RunStatus.CANCELLED,
        }
        self._runs = [
            ExecutionRun(
                id=r["id"],
                name=r["name"],
                type=r.get("type", "orchestrator"),
                status=status_map.get(r["status"], RunStatus.QUEUED),
                started_at=r.get("started_at"),
                progress_pct=r.get("progress_pct"),
                can_cancel=r.get("can_cancel", False),
            )
            for r in raw_runs
        ]
        self._refresh_list()

    def _on_refresh(self, button):
        """Refresh runs from canonical sources."""
        self._load_data()
    
    def _refresh_list(self):
        # Clear
        while True:
            child = self.runs_box.get_first_child()
            if child:
                self.runs_box.remove(child)
            else:
                break
        
        order = {
            RunStatus.FAILED: 0,
            RunStatus.RUNNING: 1,
            RunStatus.QUEUED: 2,
            RunStatus.CANCELLED: 3,
            RunStatus.COMPLETED: 4,
        }

        # Add runs, with blockers/running first and completed rows collapsed low.
        for run in sorted(self._runs, key=lambda r: (order.get(r.status, 9), r.name.lower())):
            card = ExecutionRunCard(run)
            self.runs_box.append(card)


# =============================================================================
# MAIN PAGE
# =============================================================================

class HomeConsolePage(Gtk.Box):
    """
    The ROXY Command Center Home Console.
    
    Layout: [Triage] [Talk] [Execute]
    
    This is the cockpit. Not a dashboard.
    """
    
    def __init__(self, on_navigate: Optional[callable] = None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.on_navigate = on_navigate
        self.add_css_class("home-console-page")
        
        self._build_ui()
    
    def _build_ui(self):
        # Left: Triage/Inbox column
        self.triage = TriageColumn()
        self.triage.add_css_class("sidebar-pane")
        self.append(self.triage)
        
        # Separator
        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(sep1)
        
        # Center: Talk/Roxy conversation
        self.talk = TalkColumn()
        self.append(self.talk)
        
        # Separator
        sep2 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(sep2)
        
        # Right: Execute/Progressions column
        self.execute = ExecuteColumn()
        self.execute.add_css_class("sidebar-pane")
        self.append(self.execute)
    
    def update(self, data: dict):
        """
        Update with daemon data.
        Passes performance/system telemetry to Talk and Execute columns.
        """
        if hasattr(self, "talk") and hasattr(self.talk, "update"):
            self.talk.update(data)
        if hasattr(self, "execute") and hasattr(self.execute, "update"):
            self.execute.update(data)
        pass
