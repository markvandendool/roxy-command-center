#!/usr/bin/env python3
"""
Adapter for the MindSong RCC command kernel.

This module delegates to the existing `scripts/rcc/rcc.mjs` command registry. It
does not accept raw shell input and does not create a second command registry.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from services.profile_config import load_profile


DEFAULT_TIMEOUT_S = 12.0


def _profile(profile_name: str = "friday") -> Dict[str, Any]:
    return load_profile(profile_name)


def allowed_commands(profile_name: str = "friday") -> set[str]:
    profile = _profile(profile_name)
    return set(profile.get("allowedRccCommands") or [])


def is_allowed_command(command_id: str, profile_name: str = "friday") -> bool:
    if not isinstance(command_id, str) or not command_id:
        return False
    if command_id.startswith("-") or any(ch.isspace() for ch in command_id):
        return False
    return command_id in allowed_commands(profile_name)


def run_rcc_command(
    command_id: str,
    profile_name: str = "friday",
    timeout: float = DEFAULT_TIMEOUT_S,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run an allowed RCC command through the configured command kernel."""
    profile = _profile(profile_name)
    if not is_allowed_command(command_id, profile_name):
        return {
            "ok": False,
            "commandId": command_id,
            "error": "command is not allowed for this profile",
        }

    rcc_cli = Path(profile.get("rccCli") or "")
    repo_root = Path(profile.get("repoRoot") or rcc_cli.parent.parent.parent)
    if not rcc_cli.exists():
        return {
            "ok": False,
            "commandId": command_id,
            "error": f"missing RCC CLI: {rcc_cli}",
        }

    args = ["node", str(rcc_cli), command_id, "--json"]
    if dry_run:
        args.append("--dry-run")

    try:
        cp = subprocess.run(
            args,
            cwd=str(repo_root) if repo_root.exists() else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "commandId": command_id,
            "error": "RCC command timed out",
        }
    except Exception as exc:
        return {
            "ok": False,
            "commandId": command_id,
            "error": str(exc),
        }

    parsed: Optional[Any] = None
    if cp.stdout.strip():
        try:
            parsed = json.loads(cp.stdout)
        except Exception:
            parsed = None

    return {
        "ok": cp.returncode == 0,
        "commandId": command_id,
        "returnCode": cp.returncode,
        "stdout": cp.stdout.strip(),
        "stderr": cp.stderr.strip(),
        "json": parsed,
    }


if __name__ == "__main__":
    import sys

    command = sys.argv[1] if len(sys.argv) > 1 else "roxy.status"
    print(json.dumps(run_rcc_command(command), indent=2, default=str))
