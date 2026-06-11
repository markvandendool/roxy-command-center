#!/usr/bin/env python3
"""
Mission Truth Provider — Canonical data consumer for ROXY Command Center.

Reads live canonical artifacts from the SSOT repo and maps them to Mission
and ApexLane objects. Replaces all mock/placeholder mission data.

Principle: If real data exists → consume it. Never return fake data.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# PATHS — canonical artifact locations in SSOT repo
# =============================================================================

SSOT_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")

CIVILIZATION_HEALTH_PATH = SSOT_ROOT / "public/roxy/civilization-health.json"
APEX_STATUS_PATH = SSOT_ROOT / "public/roxy/apex-status.json"
AUTHORITY_CONVERGENCE_PATH = SSOT_ROOT / "public/roxy/authority-convergence.json"
REGENT_CAMPAIGNS_DIR = SSOT_ROOT / ".git/regent/campaigns"
EPISODIC_DIGEST_PATH = SSOT_ROOT / "output/roxy/episodic-digest/latest.json"


# =============================================================================
# DATA MODELS (mirrors mission_dashboard_page.py)
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
    truth_grade: str = "unknown"  # live_probe, receipt_derived, governed_packet, stale_log
    data_source: str = "unknown"
    last_updated: str = ""


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
    truth_grade: str = "unknown"
    note: str = ""


# =============================================================================
# TRUTH PROVIDER
# =============================================================================

class MissionTruthProvider:
    """
    Reads canonical SSOT artifacts and produces live Mission/ApexLane objects.
    No probing — purely reads pre-generated canonical data.
    """

    _cache: Dict[str, Any] = {}
    _cache_time: float = 0.0
    _CACHE_TTL_SECONDS: float = 30.0

    @classmethod
    def _read_json(cls, path: Path) -> Optional[dict]:
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[MissionTruthProvider] Read error for {path}: {exc}")
            return None

    @classmethod
    def _read_campaigns(cls) -> List[dict]:
        campaigns = []
        try:
            if not REGENT_CAMPAIGNS_DIR.exists():
                return campaigns
            for f in sorted(REGENT_CAMPAIGNS_DIR.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    # Use filename as fallback ID/intent
                    if not data.get("campaignId"):
                        data["campaignId"] = f.stem
                    if not data.get("intent"):
                        data["intent"] = f.stem.replace("-", " ").replace("_", " ")
                    campaigns.append(data)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[MissionTruthProvider] Campaign read error: {exc}")
        return campaigns

    @classmethod
    def _content_hash(cls, obj: dict) -> str:
        """Stable hash for deduplication."""
        return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]

    @classmethod
    def _status_from_text(cls, text: str) -> MissionStatus:
        t = text.lower()
        if t in ("green", "healthy", "completed", "pass", "ok"):
            return MissionStatus.HEALTHY
        if t in ("amber", "warning", "warn", "degraded"):
            return MissionStatus.WARNING
        if t in ("red", "blocked", "error", "failed", "down"):
            return MissionStatus.BLOCKED
        if t in ("stalled", "orphaned", "dead", "retired"):
            return MissionStatus.STALLED
        return MissionStatus.WARNING

    @classmethod
    def _score_from_status(cls, status: MissionStatus) -> int:
        return {MissionStatus.HEALTHY: 95, MissionStatus.WARNING: 65,
                MissionStatus.BLOCKED: 25, MissionStatus.STALLED: 15,
                MissionStatus.ORPHANED: 10}.get(status, 50)

    @classmethod
    def _confidence_from_truth(cls, grade: str) -> int:
        return {"live_probe": 95, "receipt_derived": 80,
                "governed_packet": 85, "aggregated_live": 80,
                "cloud_api": 75, "stale_log": 30, "retired": 20,
                "cached_config": 25}.get(grade, 50)

    # -------------------------------------------------------------------------
    # Missions
    # -------------------------------------------------------------------------

    @classmethod
    def get_missions(cls) -> List[Mission]:
        missions: List[Mission] = []
        seen_hashes: set = set()

        # 1. Regent campaigns → missions
        # Deduplicate campaigns by campaignId, keeping most recent updatedAt
        campaigns_by_id: Dict[str, dict] = {}
        for campaign in cls._read_campaigns():
            cid = campaign.get("campaignId", "unknown")
            existing = campaigns_by_id.get(cid)
            if existing is None:
                campaigns_by_id[cid] = campaign
            else:
                # Keep the more recently updated one
                try:
                    new_ts = campaign.get("updatedAt", "")
                    old_ts = existing.get("updatedAt", "")
                    if new_ts > old_ts:
                        campaigns_by_id[cid] = campaign
                except Exception:
                    pass

        for campaign in campaigns_by_id.values():
            status_text = campaign.get("status", "unknown")
            status = cls._status_from_text(status_text)
            if status == MissionStatus.HEALTHY and status_text != "completed":
                # Active campaigns are warnings (need attention), not green
                status = MissionStatus.WARNING

            milestones = campaign.get("milestones", [])
            active_ms = [m for m in milestones if m.get("status") == "active"]
            pending_ms = [m for m in milestones if m.get("status") == "pending"]

            blockers = campaign.get("blockers", []) or []
            next_action = campaign.get("nextAction", "")
            if next_action:
                blockers.append(f"Next: {next_action}")

            missions.append(Mission(
                id=f"campaign-{campaign.get('campaignId', 'unknown')}",
                name=campaign.get("intent", "Untitled Campaign"),
                status=status,
                health_score=cls._score_from_status(status),
                confidence=cls._confidence_from_truth("receipt_derived"),
                owner=campaign.get("routedBy", "regent"),
                squad=campaign.get("assignedAgents", []) or [campaign.get("dispatchPlan", {}).get("formation", "GUARD")],
                blockers=blockers,
                receipts=len(campaign.get("receipts", [])),
                timeline=f"{len(active_ms)} active, {len(pending_ms)} pending milestones",
                priority=0 if campaign.get("urgency") == "critical" else 1,
                tags=["campaign", campaign.get("mode", "OPS").lower()],
                truth_grade="receipt_derived",
                data_source=".git/regent/campaigns",
                last_updated=campaign.get("updatedAt", ""),
            ))

        # 2. Civilization health blockers → missions
        civ = cls._read_json(CIVILIZATION_HEALTH_PATH)
        if civ:
            for blocker in civ.get("blockers", []):
                h = cls._content_hash({"type": "blocker", "text": blocker})
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                missions.append(Mission(
                    id=f"blocker-{h[:8]}",
                    name=str(blocker)[:60],
                    status=MissionStatus.BLOCKED,
                    health_score=25,
                    confidence=cls._confidence_from_truth("live_probe"),
                    owner="civilization-health",
                    squad=["roxy-health-aggregator"],
                    blockers=[str(blocker)],
                    receipts=0,
                    timeline="active",
                    priority=0,
                    tags=["blocker", "civ-health"],
                    truth_grade="live_probe",
                    data_source="public/roxy/civilization-health.json",
                    last_updated=civ.get("generatedAt", ""),
                ))

            # Subsystems with non-GREEN status → missions
            for subsys_name, subsys in civ.get("subsystems", {}).items():
                sub_status = subsys.get("status", "unknown")
                if sub_status.upper() == "GREEN":
                    continue
                h = cls._content_hash({"type": "subsys", "name": subsys_name, "status": sub_status})
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                status = cls._status_from_text(sub_status)
                # Count unhealthy lanes
                lanes = subsys.get("lanes", [])
                bad_lanes = [l for l in lanes if l.get("status") != "healthy" and l.get("status") != "available"]
                bad_names = [l.get("name", "?") for l in bad_lanes]

                missions.append(Mission(
                    id=f"subsys-{subsys_name}",
                    name=f"Subsystem: {subsys_name}",
                    status=status,
                    health_score=cls._score_from_status(status),
                    confidence=cls._confidence_from_truth("live_probe"),
                    owner="roxy-health-aggregator",
                    squad=[subsys_name],
                    blockers=bad_names if bad_names else [f"Status: {sub_status}"],
                    receipts=0,
                    timeline="ongoing",
                    priority=0 if status in (MissionStatus.BLOCKED, MissionStatus.STALLED) else 1,
                    tags=["subsystem", subsys_name],
                    truth_grade="live_probe",
                    data_source="public/roxy/civilization-health.json",
                    last_updated=civ.get("generatedAt", ""),
                ))

        # 3. Authority convergence conflicts → missions
        auth = cls._read_json(AUTHORITY_CONVERGENCE_PATH)
        if auth:
            for conflict in auth.get("conflicts", []):
                h = cls._content_hash({"type": "conflict", "data": conflict})
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                sev = conflict.get("severity", "low")
                status = MissionStatus.WARNING if sev == "low" else MissionStatus.BLOCKED
                missions.append(Mission(
                    id=f"conflict-{h[:8]}",
                    name=conflict.get("description", "Authority Conflict")[:60],
                    status=status,
                    health_score=cls._score_from_status(status),
                    confidence=cls._confidence_from_truth("governed_packet"),
                    owner="authority-convergence",
                    squad=["governance"],
                    blockers=[f"Severity: {sev}"],
                    receipts=0,
                    timeline="ongoing",
                    priority=0 if sev != "low" else 2,
                    tags=["authority", "conflict"],
                    truth_grade="governed_packet",
                    data_source="public/roxy/authority-convergence.json",
                    last_updated=auth.get("generatedAt", ""),
                ))

            # Rogue probers → mission
            rogue = auth.get("rogueProbers", [])
            if rogue:
                h = cls._content_hash({"type": "rogue", "count": len(rogue)})
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    missions.append(Mission(
                        id=f"rogue-{h[:8]}",
                        name=f"Rogue Probers: {len(rogue)} detected",
                        status=MissionStatus.WARNING,
                        health_score=50,
                        confidence=cls._confidence_from_truth("governed_packet"),
                        owner="authority-convergence",
                        squad=["governance"],
                        blockers=[f"{len(rogue)} probers writing outside canonical generators"],
                        receipts=0,
                        timeline="ongoing",
                        priority=1,
                        tags=["authority", "rogue"],
                        truth_grade="governed_packet",
                        data_source="public/roxy/authority-convergence.json",
                        last_updated=auth.get("generatedAt", ""),
                    ))

        # 4. Episodic digest → missions (recommendations as missions)
        episodic = cls._read_json(EPISODIC_DIGEST_PATH)
        if episodic:
            for rec in episodic.get("recommendations", []):
                h = cls._content_hash({"type": "episodic", "rec": rec})
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                missions.append(Mission(
                    id=f"episodic-{h[:8]}",
                    name=str(rec)[:80],
                    status=MissionStatus.WARNING,
                    health_score=60,
                    confidence=cls._confidence_from_truth("receipt_derived"),
                    owner="episodic-memory",
                    squad=["roxy-health-aggregator"],
                    blockers=[],
                    receipts=0,
                    timeline="7-day window",
                    priority=2,
                    tags=["episodic", "recommendation"],
                    truth_grade="receipt_derived",
                    data_source="output/roxy/episodic-digest/latest.json",
                    last_updated=episodic.get("generatedAt", ""),
                ))

        # Sort: critical first, then by priority
        missions.sort(key=lambda m: (m.priority, -m.health_score))
        return missions

    # -------------------------------------------------------------------------
    # Apex Lanes
    # -------------------------------------------------------------------------

    @classmethod
    def get_apex_lanes(cls) -> List[ApexLane]:
        lanes: List[ApexLane] = []
        data = cls._read_json(APEX_STATUS_PATH)
        if not data:
            return lanes

        for lane in data.get("lanes", []):
            name = lane.get("name", "unknown")
            port = lane.get("port") or 0
            model = lane.get("model", "unknown")
            status = lane.get("status", "unknown")
            truth = lane.get("truthGrade", "unknown")
            tps = lane.get("tps")
            vram = lane.get("vramMb") or 0
            gtt = lane.get("gttMb") or 0
            backend = lane.get("backend", lane.get("type", "unknown"))
            note = lane.get("note", "")

            # Determine visual status based on truth grade
            if truth == "retired":
                status = "retired"
            elif truth == "stale_log":
                status = "stale"
            elif truth in ("live_probe", "cloud_api") and status == "healthy":
                status = "healthy"

            lanes.append(ApexLane(
                name=name,
                port=port,
                model=model,
                status=status,
                tps=tps,
                vram_used_mb=vram,
                vram_total_mb=gtt or (20480 if "ada" in name.lower() else 16384 if "vulkan" in backend else 0),
                backend=backend,
                truth_grade=truth,
                note=note or "",
            ))

        return lanes

    # -------------------------------------------------------------------------
    # Orchestrator data (for home console)
    # -------------------------------------------------------------------------

    @classmethod
    def get_inbox_threads(cls) -> List[dict]:
        """Return real inbox-like items from blockers + campaigns."""
        threads = []
        seen_ids: set = set()
        civ = cls._read_json(CIVILIZATION_HEALTH_PATH)
        if civ:
            for blocker in civ.get("blockers", []):
                bid = f"blocker-{hashlib.sha256(str(blocker).encode()).hexdigest()[:8]}"
                if bid in seen_ids:
                    continue
                seen_ids.add(bid)
                threads.append({
                    "id": bid,
                    "source": "ops_alert",
                    "sender": "Civilization Health",
                    "preview": str(blocker),
                    "priority": 0,
                    "timestamp": civ.get("generatedAt", ""),
                    "suggested_action": "Investigate",
                })
        # Add campaign items as inbox threads (deduplicated by campaignId)
        campaigns_by_id: Dict[str, dict] = {}
        for campaign in cls._read_campaigns():
            cid = campaign.get("campaignId", "unknown")
            existing = campaigns_by_id.get(cid)
            if existing is None:
                campaigns_by_id[cid] = campaign
            else:
                try:
                    new_ts = campaign.get("updatedAt", "")
                    old_ts = existing.get("updatedAt", "")
                    if new_ts > old_ts:
                        campaigns_by_id[cid] = campaign
                except Exception:
                    pass
        for campaign in campaigns_by_id.values():
            if campaign.get("status") == "active":
                cid = f"campaign-{campaign.get('campaignId', 'unknown')}"
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                threads.append({
                    "id": cid,
                    "source": "orchestrator",
                    "sender": campaign.get("routedBy", "Regent"),
                    "preview": campaign.get("intent", ""),
                    "priority": 0 if campaign.get("urgency") == "critical" else 1,
                    "timestamp": campaign.get("updatedAt", ""),
                    "suggested_action": "Review",
                })
        return threads

    @classmethod
    def get_runs(cls) -> List[dict]:
        """Return execution runs from active campaigns."""
        runs = []
        for campaign in cls._read_campaigns():
            status_map = {
                "active": "running",
                "pending": "queued",
                "completed": "completed",
                "failed": "failed",
                "cancelled": "cancelled",
            }
            status = status_map.get(campaign.get("status", ""), "queued")
            milestones = campaign.get("milestones", [])
            done = sum(1 for m in milestones if m.get("status") == "completed")
            total = len(milestones)
            pct = int((done / total) * 100) if total > 0 else None

            receipts = campaign.get("receipts") or []
            receipt_path = receipts[-1] if isinstance(receipts, list) and receipts else ""
            runs.append({
                "id": campaign.get("campaignId", "unknown"),
                "name": campaign.get("intent", "Untitled"),
                "type": "orchestrator",
                "status": status,
                "started_at": campaign.get("createdAt", ""),
                "progress_pct": pct,
                "can_cancel": status == "running",
                "owner": campaign.get("routedBy", ""),
                "source": campaign.get("source", ""),
                "receipt_path": receipt_path,
            })
        return runs

    @classmethod
    def get_overview(cls) -> dict:
        """Quick status overview for home console."""
        civ = cls._read_json(CIVILIZATION_HEALTH_PATH)
        auth = cls._read_json(AUTHORITY_CONVERGENCE_PATH)
        return {
            "civilization_status": civ.get("overall", "unknown") if civ else "unknown",
            "authority_status": auth.get("overall", "unknown") if auth else "unknown",
            "active_campaigns": len([c for c in cls._read_campaigns() if c.get("status") == "active"]),
            "blockers": len(civ.get("blockers", [])) if civ else 0,
            "last_updated": civ.get("generatedAt", "") if civ else "",
        }
