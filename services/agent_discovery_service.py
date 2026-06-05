#!/usr/bin/env python3
"""
Agent Discovery Service — V5 Agent Operating Console

Responsibilities:
- Mine processes for agent-like activity (claude, codex, kimi, node agents)
- Inspect tmux/terminal sessions for agent windows
- Read git state (dirty files, HEAD, branch)
- Read lifecycle receipts from output/lifecycle-receipts/
- Generate AgentContextPacketV1 for each discovered agent
- Detect stale sessions, duplicate lanes, blocked agents
"""

import json
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any
from collections import defaultdict

# =============================================================================
# AGENT CONTEXT PACKET V1
# =============================================================================

@dataclass
class AgentContextPacketV1:
    """Canonical packet describing a live agent's state."""
    agent_id: str = ""
    lane: str = ""
    cwd: str = ""
    head: str = ""
    head_short: str = ""
    branch: str = ""
    dirty_files: List[str] = field(default_factory=list)
    dirty_count: int = 0
    active_task: str = ""
    allowed_paths: List[str] = field(default_factory=list)
    forbidden_paths: List[str] = field(default_factory=list)
    last_receipt: Optional[Dict[str, Any]] = None
    last_output: str = ""
    blocked_reason: str = ""
    next_action: str = ""
    
    # Discovered fields
    pid: int = 0
    ppid: int = 0
    tty: str = ""
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    start_time: str = ""
    session_type: str = ""  # tmux, direct, systemd, ssh
    session_name: str = ""
    child_processes: List[Dict[str, Any]] = field(default_factory=list)
    child_count: int = 0
    mcp_servers: List[str] = field(default_factory=list)
    last_activity_age_seconds: int = 0
    status: str = "unknown"  # active, idle, stale, blocked, duplicate
    health_score: int = 0  # 0-100
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# =============================================================================
# DISCOVERY ENGINE
# =============================================================================

REPO_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")
LIFECYCLE_DIR = REPO_ROOT / "output" / "lifecycle-receipts"

# Process patterns that indicate agent activity
AGENT_PATTERNS = {
    "claude": re.compile(r"\bclaude\b", re.IGNORECASE),
    "codex": re.compile(r"\bcodex\b", re.IGNORECASE),
    "kimi": re.compile(r"\bkimi\b", re.IGNORECASE),
    "gemini": re.compile(r"\bgemini\b", re.IGNORECASE),
    "cline": re.compile(r"\bcline\b", re.IGNORECASE),
    "cursor": re.compile(r"\bcursor\b", re.IGNORECASE),
}

# MCP server patterns
MCP_PATTERNS = [
    re.compile(r"mcp-.*server", re.IGNORECASE),
    re.compile(r"skill-mcp-server", re.IGNORECASE),
    re.compile(r"uss-mcp", re.IGNORECASE),
    re.compile(r"observatory-mcp", re.IGNORECASE),
    re.compile(r"blender-mcp", re.IGNORECASE),
    re.compile(r"mcp-server-", re.IGNORECASE),
]


class AgentDiscoveryService:
    """Discovers live agents and generates AgentContextPacketV1 instances."""
    
    def __init__(self):
        self._packets: List[AgentContextPacketV1] = []
        self._last_scan: Optional[datetime] = None
    
    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------
    
    def scan(self) -> List[AgentContextPacketV1]:
        """Full system scan — return list of AgentContextPacketV1."""
        packets = []
        
        # 1. Discover from tmux sessions
        tmux_agents = self._scan_tmux()
        packets.extend(tmux_agents)
        
        # 2. Discover from processes (complement tmux)
        process_agents = self._scan_processes(existing_ids={p.agent_id for p in packets})
        packets.extend(process_agents)
        
        # 3. Enrich with git state
        git_state = self._read_git_state()
        for p in packets:
            if REPO_ROOT.samefile(Path(p.cwd)) or not p.cwd:
                p.cwd = str(REPO_ROOT)
                p.head = git_state.get("head", "")
                p.head_short = p.head[:12] if p.head else ""
                p.branch = git_state.get("branch", "")
                p.dirty_files = git_state.get("dirty_files", [])
                p.dirty_count = len(p.dirty_files)
        
        # 4. Enrich with lifecycle receipts
        receipts = self._read_lifecycle_receipts()
        for p in packets:
            agent_key = p.agent_id.lower()
            matching = [r for r in receipts if agent_key in r.get("agent", "").lower()]
            if matching:
                latest = max(matching, key=lambda r: r.get("timestamp", ""))
                p.last_receipt = latest
                p.last_activity_age_seconds = self._age_seconds(latest.get("timestamp", ""))
        
        # 5. Detect duplicates and stale sessions
        packets = self._detect_anomalies(packets)
        
        # 6. Compute health scores
        for p in packets:
            p.health_score = self._compute_health(p)
        
        self._packets = packets
        self._last_scan = datetime.now()
        return packets
    
    def get_summary(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        if not self._last_scan:
            self.scan()
        
        by_status = defaultdict(int)
        by_lane = defaultdict(int)
        for p in self._packets:
            by_status[p.status] += 1
            by_lane[p.lane] += 1
        
        return {
            "scan_time": self._last_scan.isoformat() if self._last_scan else None,
            "total_agents": len(self._packets),
            "by_status": dict(by_status),
            "by_lane": dict(by_lane),
            "avg_health": sum(p.health_score for p in self._packets) / max(len(self._packets), 1),
            "blocked_count": sum(1 for p in self._packets if p.blocked_reason),
            "stale_count": sum(1 for p in self._packets if p.status == "stale"),
            "duplicate_count": sum(1 for p in self._packets if p.status == "duplicate"),
        }
    
    # -------------------------------------------------------------------------
    # Discovery methods
    # -------------------------------------------------------------------------
    
    def _scan_tmux(self) -> List[AgentContextPacketV1]:
        """Discover agents from tmux windows."""
        packets = []
        try:
            result = subprocess.run(
                ["tmux", "list-windows", "-t", "regent-command", "-F",
                 "#{window_index}|#{window_name}|#{window_active}|#{pane_pid}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return packets
            
            for line in result.stdout.strip().split("\n"):
                if "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) < 4:
                    continue
                idx, name, active, pane_pid = parts[0], parts[1], parts[2], parts[3]
                
                # Determine lane from window name
                lane = self._lane_from_name(name)
                agent_type = self._agent_type_from_name(name)
                
                pkt = AgentContextPacketV1(
                    agent_id=f"{agent_type}-{lane}-{idx}",
                    lane=lane,
                    session_type="tmux",
                    session_name=f"regent-command:{name}",
                    pid=int(pane_pid) if pane_pid.isdigit() else 0,
                    status="active" if active == "1" else "idle",
                )
                
                # Read process details for the pane PID
                self._enrich_from_ps(pkt, int(pane_pid) if pane_pid.isdigit() else None)
                
                packets.append(pkt)
                
        except Exception as e:
            print(f"[AgentDiscovery] tmux scan error: {e}")
        
        return packets
    
    def _scan_processes(self, existing_ids: set) -> List[AgentContextPacketV1]:
        """Discover agents from process list that weren't found in tmux."""
        packets = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return packets
            
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) < 11:
                    continue
                
                user, pid, cpu, mem, vsz, rss, tty, stat, start, time_cmd = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6], parts[7], parts[8], " ".join(parts[10:])
                pid = int(pid)
                cmd = time_cmd
                
                # Skip if already discovered
                if any(p.pid == pid for p in packets) or any(p.pid == pid for p in self._packets):
                    continue
                
                # Detect agent type from command
                agent_type = None
                for name, pattern in AGENT_PATTERNS.items():
                    if pattern.search(cmd):
                        agent_type = name
                        break
                
                if not agent_type:
                    continue
                
                # Skip the GTK app itself
                if "roxy-command-center" in cmd:
                    continue
                
                lane = self._lane_from_cmd(cmd)
                agent_id = f"{agent_type}-{lane}-{pid}"
                if agent_id in existing_ids:
                    continue
                
                pkt = AgentContextPacketV1(
                    agent_id=agent_id,
                    lane=lane,
                    pid=pid,
                    cpu_percent=float(cpu),
                    mem_percent=float(mem),
                    tty=tty if tty != "?" else "",
                    start_time=start,
                    session_type="direct",
                    status="active",
                )
                
                # Find child MCP servers
                pkt.mcp_servers = self._find_mcp_servers(pid)
                pkt.child_count = len(pkt.mcp_servers)
                
                packets.append(pkt)
                
        except Exception as e:
            print(f"[AgentDiscovery] process scan error: {e}")
        
        return packets
    
    def _read_git_state(self) -> Dict[str, Any]:
        """Read git state from canonical repo."""
        state = {"head": "", "branch": "", "dirty_files": []}
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                state["head"] = result.stdout.strip()
            
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                state["branch"] = result.stdout.strip()
            
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                state["dirty_files"] = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                
        except Exception as e:
            print(f"[AgentDiscovery] git scan error: {e}")
        
        return state
    
    def _read_lifecycle_receipts(self) -> List[Dict[str, Any]]:
        """Read lifecycle receipts from output/lifecycle-receipts/."""
        receipts = []
        try:
            if not LIFECYCLE_DIR.exists():
                return receipts
            
            for date_dir in LIFECYCLE_DIR.iterdir():
                if not date_dir.is_dir():
                    continue
                for receipt_file in date_dir.glob("*.json"):
                    try:
                        data = json.loads(receipt_file.read_text())
                        data["_file"] = str(receipt_file)
                        receipts.append(data)
                    except Exception:
                        pass
                        
        except Exception as e:
            print(f"[AgentDiscovery] receipt scan error: {e}")
        
        return receipts
    
    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    
    def _lane_from_name(self, name: str) -> str:
        """Extract lane from tmux window name."""
        if "regent" in name.lower():
            return "regent"
        if "architect" in name.lower():
            return "architect"
        if "workhorse" in name.lower():
            return "workhorse"
        if "research" in name.lower():
            return "research"
        if "primary" in name.lower():
            return "primary"
        if "factory" in name.lower():
            return "factory"
        if "testing" in name.lower():
            return "testing"
        if "shell" in name.lower():
            return "ops"
        if "logs" in name.lower():
            return "logs"
        return "unknown"
    
    def _agent_type_from_name(self, name: str) -> str:
        """Extract agent type from tmux window name."""
        name_lower = name.lower()
        for agent_type in ["claude", "codex", "kimi", "gemini", "cline", "cursor"]:
            if agent_type in name_lower:
                return agent_type
        return "unknown"
    
    def _lane_from_cmd(self, cmd: str) -> str:
        """Extract lane from process command."""
        cmd_lower = cmd.lower()
        if "regent" in cmd_lower:
            return "regent"
        if "bridge" in cmd_lower:
            return "bridge"
        if "mcp" in cmd_lower:
            return "mcp"
        return "direct"
    
    def _enrich_from_ps(self, pkt: AgentContextPacketV1, pid: Optional[int]):
        """Read process details from ps for a given PID."""
        if not pid:
            return
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "%cpu,%mem,tty,stat,lstart,comm"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    parts = lines[1].split()
                    if len(parts) >= 6:
                        pkt.cpu_percent = float(parts[0])
                        pkt.mem_percent = float(parts[1])
                        pkt.tty = parts[2] if parts[2] != "?" else ""
        except Exception:
            pass
    
    def _find_mcp_servers(self, parent_pid: int) -> List[str]:
        """Find MCP server child processes of a given PID."""
        servers = []
        try:
            result = subprocess.run(
                ["pgrep", "-P", str(parent_pid)],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return servers
            
            for child_pid in result.stdout.strip().split("\n"):
                if not child_pid.strip():
                    continue
                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", child_pid.strip(), "-o", "comm="],
                        capture_output=True, text=True, timeout=2
                    )
                    if ps_result.returncode == 0:
                        cmd = ps_result.stdout.strip()
                        for pattern in MCP_PATTERNS:
                            if pattern.search(cmd):
                                servers.append(cmd)
                                break
                except Exception:
                    pass
                    
        except Exception:
            pass
        
        return servers
    
    def _age_seconds(self, timestamp_str: str) -> int:
        """Compute age in seconds from ISO timestamp."""
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return int((datetime.now(ts.tzinfo) - ts).total_seconds())
        except Exception:
            return 0
    
    def _detect_anomalies(self, packets: List[AgentContextPacketV1]) -> List[AgentContextPacketV1]:
        """Detect stale sessions and duplicate lanes."""
        # Mark stale (> 1 hour no activity)
        for p in packets:
            if p.last_activity_age_seconds > 3600:
                p.status = "stale"
                p.blocked_reason = "No activity for >1 hour"
        
        # Detect duplicates (same lane, same agent type)
        lane_type_counts = defaultdict(list)
        for p in packets:
            key = (p.lane, self._agent_type_from_name(p.agent_id))
            lane_type_counts[key].append(p)
        
        for key, group in lane_type_counts.items():
            if len(group) > 1:
                # Mark all but the most recent as duplicate
                sorted_group = sorted(group, key=lambda p: p.last_activity_age_seconds)
                for p in sorted_group[:-1]:
                    if p.status == "active":
                        p.status = "duplicate"
                        p.blocked_reason = f"Duplicate of {sorted_group[-1].agent_id}"
        
        return packets
    
    def _compute_health(self, p: AgentContextPacketV1) -> int:
        """Compute health score 0-100."""
        score = 100
        
        if p.status == "stale":
            score -= 40
        if p.status == "duplicate":
            score -= 30
        if p.blocked_reason:
            score -= 25
        if p.dirty_count > 20:
            score -= 10
        if not p.last_receipt:
            score -= 15
        if p.last_activity_age_seconds > 1800:
            score -= 10
        
        return max(0, score)


# =============================================================================
# CLI / test
# =============================================================================

if __name__ == "__main__":
    svc = AgentDiscoveryService()
    packets = svc.scan()
    
    print("=" * 60)
    print(f"AGENT DISCOVERY SCAN — {len(packets)} agents found")
    print("=" * 60)
    
    for p in packets:
        print(f"\n🤖 {p.agent_id}")
        print(f"   Lane: {p.lane} | Status: {p.status} | Health: {p.health_score}/100")
        print(f"   PID: {p.pid} | TTY: {p.tty or 'none'} | Session: {p.session_type}")
        print(f"   CPU: {p.cpu_percent}% | MEM: {p.mem_percent}% | Start: {p.start_time}")
        print(f"   HEAD: {p.head_short} | Branch: {p.branch} | Dirty: {p.dirty_count}")
        if p.mcp_servers:
            print(f"   MCPs: {', '.join(p.mcp_servers[:5])}")
        if p.blocked_reason:
            print(f"   ⚠️  Blocked: {p.blocked_reason}")
        if p.last_receipt:
            print(f"   📄 Last receipt: {p.last_receipt.get('_file', 'unknown')}")
    
    summary = svc.get_summary()
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k}: {v}")
