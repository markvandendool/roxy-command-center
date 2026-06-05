#!/usr/bin/env python3
"""
Command Center Dirty-State Guard.

Classifies dirty files so roxy-core can explain its state.
No mutations — read-only classification.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).parent.parent.parent


def run_git(args: List[str]) -> Tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT)] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def classify_dirty():
    rc, stdout, stderr = run_git(["status", "--short"])
    if rc != 0:
        print(f"git status failed: {stderr}")
        sys.exit(1)

    lines = [l.rstrip('\n') for l in stdout.splitlines() if l.strip()]

    categories = {
        "source_dirt": [],
        "runtime_dirt": [],
        "pycache_dirt": [],
        "plan_doc_dirt": [],
        "unknown_artifacts": [],
    }

    for line in lines:
        status = line[:2]
        path = line[3:].strip()

        if "__pycache__" in path or path.endswith(".pyc"):
            categories["pycache_dirt"].append((status, path))
        elif path.startswith("output/") or path.startswith("runtime/"):
            categories["runtime_dirt"].append((status, path))
        elif path.endswith(".md") and ("PLAN" in path or "WIRING" in path or "AUDIT" in path):
            categories["plan_doc_dirt"].append((status, path))
        elif path.startswith(("widgets/", "services/", "ui/", "main.py")):
            categories["source_dirt"].append((status, path))
        else:
            categories["unknown_artifacts"].append((status, path))

    print("=" * 60)
    print("Command Center Dirty-State Report")
    print("=" * 60)
    print(f"Total dirty files: {len(lines)}")
    print()

    for name, items in categories.items():
        if items:
            print(f"{name}: {len(items)}")
            for status, path in items[:10]:
                print(f"  [{status}] {path}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")
            print()

    print("-" * 60)
    if not lines:
        print("✅ Working tree is clean.")
    elif len(categories["unknown_artifacts"]) == 0 and len(categories["source_dirt"]) == 0:
        print("⚠️ Only runtime/pycache drift — safe to ignore for source authority.")
    else:
        print("🔴 Source or unknown artifacts present — review before claiming clean.")
    print("-" * 60)


if __name__ == "__main__":
    classify_dirty()
