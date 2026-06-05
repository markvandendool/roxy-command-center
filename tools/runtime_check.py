#!/usr/bin/env python3
"""Runtime dependency check for ROXY Command Center current-runtime adaptation."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


def run(command: list[str], timeout: float = 8.0) -> dict:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_gi() -> dict:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("Soup", "3.0")
        from gi.repository import Adw, Gtk, Soup  # noqa: F401

        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def check_ollama() -> dict:
    url = "http://127.0.0.1:11434/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            payload = json.loads(response.read().decode())
        models = [m.get("name", "unknown") for m in payload.get("models", [])]
        return {"ok": True, "url": url, "models": models}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def main() -> int:
    docker_info = run(["docker", "info", "--format", "{{.DockerRootDir}}"], timeout=8.0)
    report = {
        "python": {
            "ok": sys.version_info >= (3, 10),
            "version": sys.version,
        },
        "gtk_libadwaita_soup": check_gi(),
        "ollama_api": check_ollama(),
        "roxy_law0": run(["/opt/roxy/bin/roxy-law0"], timeout=12.0),
        "roxy_external_guard": run(["/opt/roxy/bin/roxy-external-guard"], timeout=12.0),
        "work_mount": run(["findmnt", "/mnt/work"], timeout=5.0),
        "docker_root": docker_info,
        "docker_binary": {"ok": shutil.which("docker") is not None, "path": shutil.which("docker")},
        "roxy_safety_mount": run(["findmnt", "/media/mark/ROXY_SAFETY"], timeout=5.0),
        "app_path": str(Path(__file__).resolve().parents[1]),
    }

    # findmnt returns nonzero when the unsafe volume is absent, which is desired.
    report["roxy_safety_not_mounted"] = {"ok": not report["roxy_safety_mount"].get("ok", False)}

    checks = [
        report["python"]["ok"],
        report["gtk_libadwaita_soup"]["ok"],
        report["ollama_api"]["ok"],
        report["roxy_law0"]["ok"],
        report["roxy_external_guard"]["ok"],
        report["work_mount"]["ok"],
        report["docker_root"]["ok"] and "/mnt/work/containers/docker" in report["docker_root"].get("stdout", ""),
        report["roxy_safety_not_mounted"]["ok"],
    ]
    report["ok"] = all(checks)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
