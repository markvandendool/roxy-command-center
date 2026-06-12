#!/usr/bin/env python3
"""
Profile configuration for Roxy Command Center deployments.

Profiles are local UI/deployment constraints. They do not grant source authority
or create command authority. Missing or malformed profile data fails closed for
source authority and mutating controls.
"""

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


APP_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = APP_ROOT / "profiles"

DEFAULT_PROFILE: Dict[str, Any] = {
    "profileId": "roxy-default",
    "displayName": "Roxy Command Center",
    "modeLabel": "LOCAL",
    "sourceAuthority": False,
    "repoRoot": "/mnt/work/ssot/mindsong-juke-hub",
    "rccCli": "/mnt/work/ssot/mindsong-juke-hub/scripts/rcc/rcc.mjs",
    "statusCommand": "",
    "enabledPages": [],
    "disabledPages": [],
    "forbiddenActions": [
        "arbitrary_shell",
        "git_commit",
        "git_push",
        "source_write",
        "secret_read",
    ],
    "allowedRccCommands": [],
}


def _normalize_profile_name(profile_name: Optional[str]) -> str:
    name = (profile_name or os.environ.get("RCC_PROFILE") or "default").strip()
    return name or "default"


def _merge_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    profile = deepcopy(DEFAULT_PROFILE)
    profile.update(raw)

    # Fail closed unless explicitly true. Profiles like Friday must never inherit
    # source authority by omission or malformed data.
    profile["sourceAuthority"] = profile.get("sourceAuthority") is True

    for key in ("enabledPages", "disabledPages", "forbiddenActions", "allowedRccCommands"):
        value = profile.get(key)
        if not isinstance(value, list):
            profile[key] = []
        else:
            profile[key] = [str(item) for item in value]

    return profile


def load_profile(profile_name: Optional[str] = None) -> Dict[str, Any]:
    """Load the named profile. Missing profiles degrade to the safe default."""
    name = _normalize_profile_name(profile_name)
    if name in {"default", "roxy", "roxy-default"}:
        return deepcopy(DEFAULT_PROFILE)

    path = PROFILES_DIR / f"{name}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return deepcopy(DEFAULT_PROFILE)
        return _merge_profile(raw)
    except Exception as exc:
        profile = deepcopy(DEFAULT_PROFILE)
        profile["profileId"] = f"missing-{name}"
        profile["displayName"] = f"Missing profile: {name}"
        profile["profileError"] = str(exc)
        profile["sourceAuthority"] = False
        return profile


def profile_allows_page(profile: Dict[str, Any], page_id: str) -> bool:
    """Return whether a page should be reachable for the active profile."""
    disabled = set(profile.get("disabledPages") or [])
    if page_id in disabled:
        return False

    enabled = set(profile.get("enabledPages") or [])
    if enabled:
        return page_id in enabled

    return True


def active_profile() -> Dict[str, Any]:
    """Convenience wrapper for environment-selected profile."""
    return load_profile()
