#!/usr/bin/env python3
"""
RCC Adapter — Thin Python wrapper over the SSOT RCC Command Kernel.

This adapter makes the GTK4 Command Center a client of the canonical
RCC command bus. No command logic lives here. All commands are dispatched
to scripts/rcc/rcc.mjs in the SSOT repo.

Usage:
    from services.rcc_adapter import RCCAdapter
    adapter = RCCAdapter()
    commands = adapter.list_commands()
    result = adapter.run("roxy.status", json_output=True)
    receipt = adapter.read_latest_receipt("roxy.status")
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

SSOT_ROOT = Path("/mnt/work/ssot/mindsong-juke-hub")
RCC_CLI = SSOT_ROOT / "scripts" / "rcc" / "rcc.mjs"
RCC_RECEIPT_ROOT = SSOT_ROOT / "output" / "rcc" / "receipts"
COMMAND_TIMEOUTS = {
    "factory.routes": 120.0,
}


@dataclass
class RCCCommandMeta:
    """Metadata for a single RCC command."""
    id: str
    label: str
    namespace: str
    world: str
    risk_tier: str


@dataclass
class RCCRunResult:
    """Result of running an RCC command."""
    ok: bool
    verdict: str
    data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    next_action: Optional[str] = None
    receipt_path: Optional[str] = None
    duration_ms: int = 0
    raw_json: Optional[dict] = None


@dataclass
class RCCReceiptSummary:
    """Summary of an RCC receipt."""
    command_id: str
    run_id: str
    finished_at: str
    verdict: str
    duration_ms: int
    path: Optional[Path] = None


class RCCAdapter:
    """
    Thin adapter that delegates all command execution to the RCC CLI.

    No command logic, no registry, no state. Pure delegation + parsing.
    """

    def __init__(self, ssot_root: Path = SSOT_ROOT):
        self.ssot_root = Path(ssot_root)
        self.rcc_cli = self.ssot_root / "scripts" / "rcc" / "rcc.mjs"
        self.receipt_root = self.ssot_root / "output" / "rcc" / "receipts"

    def _run_rcc(self, *args: str, timeout: float = 30.0) -> dict[str, Any]:
        """Invoke the RCC CLI and parse JSON output."""
        cmd = ["node", str(self.rcc_cli), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.ssot_root),
            )
            # RCC --json outputs JSON to stdout
            # Non-JSON outputs human text; we try to parse JSON from stdout
            stdout = result.stdout.strip()
            if stdout:
                try:
                    return {"ok": True, "json": json.loads(stdout), "stderr": result.stderr}
                except json.JSONDecodeError:
                    return {"ok": result.returncode == 0, "text": stdout, "stderr": result.stderr, "returncode": result.returncode}
            return {"ok": result.returncode == 0, "text": "", "stderr": result.stderr, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"RCC timed out after {timeout}s", "text": "", "stderr": ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "text": "", "stderr": ""}

    def list_commands(self) -> list[RCCCommandMeta]:
        """Return all registered RCC commands."""
        result = self._run_rcc("--list")
        if not result.get("ok"):
            return []

        # Parse the human-readable list output
        # Format: "roxy.status         T0  moon        Roxy machine state"
        commands = []
        text = result.get("text", "")
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("RCC") or line.startswith("="):
                continue
            parts = line.split(None, 3)
            if len(parts) >= 4:
                commands.append(RCCCommandMeta(
                    id=parts[0],
                    label=parts[3],
                    namespace=parts[0].split(".")[0] if "." in parts[0] else "unknown",
                    world=parts[2],
                    risk_tier=parts[1],
                ))
        return commands

    def explain(self, command_id: str) -> dict[str, Any]:
        """Return human + schema docs for a command."""
        result = self._run_rcc("--explain", command_id)
        return {"ok": result.get("ok", False), "text": result.get("text", "")}

    def dry_run(self, command_id: str) -> RCCRunResult:
        """Dry-run a command (plan only, no execution)."""
        return self.run(command_id, dry_run=True)

    def run(self, command_id: str, *, dry_run: bool = False, receipt: bool = False, json_output: bool = True) -> RCCRunResult:
        """Execute an RCC command and return structured result."""
        args = [command_id]
        if json_output:
            args.append("--json")
        if dry_run:
            args.append("--dry-run")
        if receipt:
            args.append("--receipt")

        result = self._run_rcc(*args, timeout=COMMAND_TIMEOUTS.get(command_id, 30.0))

        if "json" in result:
            j = result["json"]
            return RCCRunResult(
                ok=j.get("ok", False),
                verdict=j.get("verdict", "UNKNOWN"),
                data=j.get("data", {}),
                warnings=j.get("warnings", []),
                errors=j.get("errors", []),
                next_action=j.get("nextAction"),
                receipt_path=j.get("receiptPath"),
                duration_ms=j.get("durationMs", 0),
                raw_json=j,
            )

        # Fallback for non-JSON output
        return RCCRunResult(
            ok=result.get("ok", False),
            verdict="UNKNOWN",
            data={},
            warnings=[result.get("stderr", "")] if result.get("stderr") else [],
            errors=[result.get("error", "")] if result.get("error") else [],
            raw_json=result,
        )

    def read_latest_receipt(self, command_id: str) -> Optional[RCCReceiptSummary]:
        """Read the latest receipt for a command from the RCC receipt tree."""
        safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in command_id)
        cmd_dir = self.receipt_root / safe_id
        if not cmd_dir.exists():
            return None

        try:
            files = sorted(cmd_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return None
            latest = files[0]
            data = json.loads(latest.read_text(encoding="utf-8"))
            return RCCReceiptSummary(
                command_id=data.get("commandId", command_id),
                run_id=data.get("runId", "unknown"),
                finished_at=data.get("finishedAt", ""),
                verdict=data.get("result", {}).get("verdict", "UNKNOWN"),
                duration_ms=data.get("durationMs", 0),
                path=latest,
            )
        except Exception:
            return None

    def list_receipts(self, command_id: Optional[str] = None, limit: int = 20) -> list[RCCReceiptSummary]:
        """List receipts, optionally filtered by command."""
        summaries = []
        if not self.receipt_root.exists():
            return summaries
        dirs = [self.receipt_root / command_id] if command_id else [d for d in self.receipt_root.iterdir() if d.is_dir()]

        for cmd_dir in dirs:
            if not cmd_dir.exists():
                continue
            try:
                files = sorted(cmd_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
                for f in files:
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        summaries.append(RCCReceiptSummary(
                            command_id=data.get("commandId", cmd_dir.name),
                            run_id=data.get("runId", "unknown"),
                            finished_at=data.get("finishedAt", ""),
                            verdict=data.get("result", {}).get("verdict", "UNKNOWN"),
                            duration_ms=data.get("durationMs", 0),
                            path=f,
                        ))
                    except Exception:
                        pass
            except Exception:
                pass

        summaries.sort(key=lambda s: s.finished_at, reverse=True)
        return summaries[:limit]

    def status(self) -> dict[str, Any]:
        """Quick adapter health check."""
        return {
            "ssot_root_exists": self.ssot_root.exists(),
            "rcc_cli_exists": self.rcc_cli.exists(),
            "receipt_root_exists": self.receipt_root.exists(),
            "ssot_root": str(self.ssot_root),
            "rcc_cli": str(self.rcc_cli),
        }
