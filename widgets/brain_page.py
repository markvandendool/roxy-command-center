#!/usr/bin/env python3
"""
Brain Page — ROXY self-knowledge, authority, and capability surface.
Answers: Who am I? What do I know? What can I do? What governs me?
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Dict, Any


class BrainCard(Gtk.Box):
    """Card showing a brain metric with value, subtitle, and status color."""

    def __init__(self, title: str, icon_name: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("overview-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(header)

        if icon_name:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(20)
            header.append(icon)

        title_lbl = Gtk.Label(label=title)
        title_lbl.add_css_class("overview-title")
        title_lbl.set_xalign(0)
        title_lbl.set_hexpand(True)
        header.append(title_lbl)

        self.value_label = Gtk.Label(label="--")
        self.value_label.add_css_class("overview-value")
        self.value_label.set_xalign(0)
        self.append(self.value_label)

        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.add_css_class("overview-subtitle")
        self.subtitle_label.set_xalign(0)
        self.append(self.subtitle_label)

    def set(self, value: str, subtitle: str = "", status: str = "healthy"):
        self.value_label.set_label(value)
        self.subtitle_label.set_label(subtitle)
        self.remove_css_class("status-healthy")
        self.remove_css_class("status-warn")
        self.remove_css_class("status-blocked")
        if status in ("healthy", "warn", "blocked"):
            self.add_css_class(f"status-{status}")


class BrainPage(Gtk.ScrolledWindow):
    """ROXY brain health dashboard — authoritative self-knowledge surface."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._cards: Dict[str, BrainCard] = {}
        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(24)
        main_box.set_margin_end(24)
        self.set_child(main_box)

        title = Gtk.Label(label="Brain")
        title.add_css_class("title-1")
        title.set_xalign(0)
        main_box.append(title)

        # ─── SELF: Who am I? ───
        self_title = Gtk.Label(label="Self — Identity & Hardware")
        self_title.add_css_class("moc-section-label")
        self_title.set_xalign(0)
        main_box.append(self_title)

        self_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self_box.set_homogeneous(True)
        main_box.append(self_box)

        for key, label, icon in [
            ("self_model", "Model", "cpu-symbolic"),
            ("self_lane", "Lane", "media-playback-start-symbolic"),
            ("self_tps", "Throughput", "speedometer-symbolic"),
            ("self_latency", "Latency", "network-transmit-receive-symbolic"),
        ]:
            card = BrainCard(label, icon)
            self._cards[key] = card
            self_box.append(card)

        # ─── KNOWLEDGE: What do I know? ───
        know_title = Gtk.Label(label="Knowledge — Memory & Vector Store")
        know_title.add_css_class("moc-section-label")
        know_title.set_xalign(0)
        know_title.set_margin_top(16)
        main_box.append(know_title)

        know_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        know_box.set_homogeneous(True)
        main_box.append(know_box)

        for key, label, icon in [
            ("know_sessions", "Sessions", "document-open-symbolic"),
            ("know_messages", "Messages", "mail-read-symbolic"),
            ("know_vectors", "Vectors", "view-list-symbolic"),
            ("know_skills", "Skills", "preferences-system-symbolic"),
        ]:
            card = BrainCard(label, icon)
            self._cards[key] = card
            know_box.append(card)

        # ─── CAPABILITY: What can I do? ───
        cap_title = Gtk.Label(label="Capability — Tools & Services")
        cap_title.add_css_class("moc-section-label")
        cap_title.set_xalign(0)
        cap_title.set_margin_top(16)
        main_box.append(cap_title)

        cap_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        cap_box.set_homogeneous(True)
        main_box.append(cap_box)

        for key, label, icon in [
            ("cap_gateway", "Gateway", "network-server-symbolic"),
            ("cap_mcp", "MCP", "preferences-system-symbolic"),
            ("cap_agents", "Agents", "user-available-symbolic"),
            ("cap_qdrant", "Qdrant", "database-symbolic"),
        ]:
            card = BrainCard(label, icon)
            self._cards[key] = card
            cap_box.append(card)

        # ─── AUTHORITY: What governs me? ───
        auth_title = Gtk.Label(label="Authority — Doctrine & Governance")
        auth_title.add_css_class("moc-section-label")
        auth_title.set_xalign(0)
        auth_title.set_margin_top(16)
        main_box.append(auth_title)

        auth_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        auth_box.set_homogeneous(True)
        main_box.append(auth_box)

        for key, label, icon in [
            ("auth_brain", "Brain Auth", "security-high-symbolic"),
            ("auth_judge", "Judge Auth", "emblem-ok-symbolic"),
            ("auth_harness", "Harness", "channel-secure-symbolic"),
            ("auth_closure", "Sovereignty", "starred-symbolic"),
        ]:
            card = BrainCard(label, icon)
            self._cards[key] = card
            auth_box.append(card)

        # ─── DOCTRINE LINE ───
        doctrine_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        doctrine_box.set_margin_top(8)
        main_box.append(doctrine_box)

        self.doctrine_label = Gtk.Label(label="")
        self.doctrine_label.add_css_class("monospace")
        self.doctrine_label.set_xalign(0)
        self.doctrine_label.set_wrap(True)
        doctrine_box.append(self.doctrine_label)

    def _val(self, data: dict, *path: str, fallback: str = "UNKNOWN") -> str:
        obj = data
        for key in path:
            if not isinstance(obj, dict) or key not in obj:
                return f"{fallback} (key: {'.'.join(path)})"
            obj = obj[key]
        if obj is None or obj == "":
            return f"{fallback} (key: {'.'.join(path)})"
        return str(obj)

    def _num(self, data: dict, *path: str, fallback: Any = None) -> Optional[Any]:
        obj = data
        for key in path:
            if not isinstance(obj, dict) or key not in obj:
                return fallback
            obj = obj[key]
        return obj if isinstance(obj, (int, float)) else fallback

    def update(self, data: dict):
        brain = data.get("brainAuthority", {})
        judge = data.get("judgeAuthority", {})
        qdrant = data.get("qdrant", {})
        gateway = data.get("gateway", {})
        lanes = data.get("lanes", [])
        perf = data.get("performance", {})
        perf_agents = perf.get("agents", {})
        perf_mcp = perf.get("mcp", {})
        sovereign = data.get("sovereignClosure", {})

        # Live sources (queried directly by daemon_client)
        live_qdrant = data.get("_live_qdrant", {})
        live_proxy = data.get("_live_proxy", {})
        live_latency = data.get("_live_latency", {})

        # ─── SELF ───
        # Find ROXY's own lane (Ada Coder Frontier or first healthy lane with tps)
        roxy_lane = None
        for lane in lanes:
            if "frontier" in lane.get("name", "").lower() or "ada" in lane.get("name", "").lower():
                roxy_lane = lane
                break
        if not roxy_lane:
            roxy_lane = next((l for l in lanes if l.get("status") == "healthy" and l.get("tps")), None)
        if not roxy_lane:
            roxy_lane = lanes[0] if lanes else {}

        model_name = roxy_lane.get("model", "—") if roxy_lane else "—"
        gpu_name = roxy_lane.get("gpu", "—") if roxy_lane else "—"
        quant = roxy_lane.get("quantization", "—") if roxy_lane else "—"
        params = roxy_lane.get("parametersB", 0) if roxy_lane else 0
        params_str = f"{params}B" if params else "—"

        if "self_model" in self._cards:
            self._cards["self_model"].set(
                model_name,
                f"{params_str} · {quant}",
                "healthy" if roxy_lane and roxy_lane.get("status") == "healthy" else "warn"
            )

        lane_name = roxy_lane.get("name", "—") if roxy_lane else "—"
        lane_role = roxy_lane.get("role", "—") if roxy_lane else "—"
        if "self_lane" in self._cards:
            self._cards["self_lane"].set(
                lane_name,
                f"{gpu_name} · {lane_role}",
                "healthy" if roxy_lane and roxy_lane.get("status") == "healthy" else "warn"
            )

        tps = roxy_lane.get("tps") if roxy_lane else None
        prompt_tps = roxy_lane.get("promptTps") if roxy_lane else None
        tps_str = f"{tps} t/s" if tps else "—"
        if "self_tps" in self._cards:
            self._cards["self_tps"].set(
                tps_str,
                f"Prompt {prompt_tps or '—'} t/s" if prompt_tps else "Inference throughput",
                "healthy" if tps else "warn"
            )

        lat = live_latency.get("latency_ms")
        lat_reachable = live_latency.get("reachable", False)
        if "self_latency" in self._cards:
            self._cards["self_latency"].set(
                f"{lat} ms" if lat else ("Online" if lat_reachable else "Offline"),
                "Proxy health ping · no generation" if lat else (live_latency.get("error", "—")[:40]),
                "healthy" if lat and lat < 5000 else "warn" if lat_reachable else "blocked"
            )

        # ─── KNOWLEDGE ───
        # Prefer live proxy storage counts over apex snapshot (more accurate)
        storage = live_proxy.get("storage", {}) if live_proxy.get("reachable") else {}
        storage_counts = storage.get("counts", {})

        sessions = storage_counts.get("sessions") if storage_counts else self._num(brain, "realBrain", "sessions")
        messages = storage_counts.get("messages") if storage_counts else self._num(brain, "realBrain", "messages")
        mem_cands = storage_counts.get("memoryCandidates") if storage_counts else self._num(brain, "realBrain", "memoryCandidates")
        promoted = storage_counts.get("promotedMemoryCandidates") if storage_counts else self._num(brain, "realBrain", "promoted")

        if "know_sessions" in self._cards:
            self._cards["know_sessions"].set(
                str(sessions) if sessions is not None else "—",
                "SQLite sessions",
                "healthy" if sessions else "warn"
            )
        if "know_messages" in self._cards:
            self._cards["know_messages"].set(
                str(messages) if messages is not None else "—",
                "Total messages",
                "healthy" if messages else "warn"
            )
        if "know_vectors" in self._cards:
            vec_count = live_qdrant.get("indexed_vectors_count") if live_qdrant.get("reachable") else None
            if vec_count is None:
                vec_count = qdrant.get("pointsCount") or qdrant.get("points_count")
            self._cards["know_vectors"].set(
                f"{vec_count:,}" if vec_count else "—",
                "Qdrant indexed vectors",
                "healthy" if live_qdrant.get("reachable") else "warn"
            )
        if "know_skills" in self._cards:
            skill_docs = live_proxy.get("skill_docs", 0) if live_proxy.get("reachable") else 0
            skill_emb = live_proxy.get("skill_embeddings_loaded", False)
            self._cards["know_skills"].set(
                str(skill_docs),
                f"Embeddings {'loaded' if skill_emb else 'missing'}",
                "healthy" if skill_docs > 0 and skill_emb else "warn"
            )

        # ─── CAPABILITY ───
        gw_port = gateway.get("port", 4000)
        gw_models = gateway.get("models", 0)
        gw_ok = gateway.get("status") == "healthy" or live_proxy.get("upstream_reachable", False)
        if "cap_gateway" in self._cards:
            self._cards["cap_gateway"].set(
                f":{gw_port}",
                f"{gw_models} models · LiteLLM",
                "healthy" if gw_ok else "blocked"
            )

        mcp_total = perf_mcp.get("total", 0) if isinstance(perf_mcp, dict) else 0
        if "cap_mcp" in self._cards:
            self._cards["cap_mcp"].set(
                str(mcp_total),
                "MCP processes",
                "healthy" if mcp_total > 0 else "warn"
            )

        agents_total = perf_agents.get("total", 0) if isinstance(perf_agents, dict) else 0
        agents_active = perf_agents.get("active", 0) if isinstance(perf_agents, dict) else 0
        if "cap_agents" in self._cards:
            self._cards["cap_agents"].set(
                f"{agents_active}/{agents_total}",
                "Active agents",
                "healthy" if agents_active > 0 else "warn"
            )

        qdrant_ok = live_qdrant.get("reachable", False) or qdrant.get("status") == "healthy"
        qdrant_url = qdrant.get("url", "http://127.0.0.1:3002")
        if "cap_qdrant" in self._cards:
            self._cards["cap_qdrant"].set(
                "Healthy" if qdrant_ok else "Down",
                qdrant_url,
                "healthy" if qdrant_ok else "blocked"
            )

        # ─── AUTHORITY ───
        brain_ok = brain.get("status") == "healthy"
        brain_verdict = brain.get("verdict", "—")
        if "auth_brain" in self._cards:
            self._cards["auth_brain"].set(
                brain_verdict,
                (brain.get("note", "") or "Brain authority")[:50],
                "healthy" if brain_ok else "warn"
            )

        judge_ok = judge.get("status") == "healthy"
        judge_verdict = judge.get("verdict", "—")
        rep = judge.get("reputation", {})
        pass_rate = rep.get("passRate", 0)
        if "auth_judge" in self._cards:
            self._cards["auth_judge"].set(
                judge_verdict,
                f"Pass rate {pass_rate:.0%}",
                "healthy" if judge_ok else "warn"
            )

        # Harness integrity: check if proxy reports bypass detection
        harness_clean = True
        harness_note = "Identity enforcement active"
        # The proxy now sets harnessBypassDetected in roxy metadata;
        # we don't have per-response access here, but we can check prompt loaded status
        if live_proxy.get("reachable") and not live_proxy.get("prompt_loaded"):
            harness_clean = False
            harness_note = "System prompt not loaded — harness degraded"
        if "auth_harness" in self._cards:
            self._cards["auth_harness"].set(
                "Clean" if harness_clean else "Degraded",
                harness_note,
                "healthy" if harness_clean else "danger"
            )

        sov_score = sovereign.get("sovereignty", 0)
        proof_cov = sovereign.get("proofCoverage", 0)
        if "auth_closure" in self._cards:
            self._cards["auth_closure"].set(
                f"{sov_score}",
                f"Proof coverage {proof_cov}%",
                "healthy" if sov_score >= 70 else "warn"
            )

        # Doctrine line
        doctrine_parts = []
        if brain.get("crossProcessRecall"):
            doctrine_parts.append("Cross-process recall: ON")
        if sovereign.get("discoveryDebt", {}).get("drift", 0):
            doctrine_parts.append(f"Drift: {sovereign['discoveryDebt']['drift']}")
        if live_proxy.get("max_tokens_floor"):
            doctrine_parts.append(f"Token floor: {live_proxy['max_tokens_floor']}")
        self.doctrine_label.set_label(" · ".join(doctrine_parts) if doctrine_parts else "Doctrine: Law 0 active · No drift detected")
