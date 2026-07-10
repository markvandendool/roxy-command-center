#!/usr/bin/env python3
"""Runtime dependency and native-process health checks for ROXY Command Center."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


APP_ID = "org.roxy.CommandCenter"
APP_OBJECT_PATH = "/org/roxy/CommandCenter"
APP_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = Path.home() / ".local" / "bin" / "roxy-command-center"
RUNTIME_DIR = Path.home() / ".cache" / "roxy-command-center"
RECEIPT_DIR = RUNTIME_DIR / "launch-receipts"

DEFAULT_BACKEND_TARGETS = {
    "operatorKernel": "http://127.0.0.1:9135/health",
    "bridge": "http://127.0.0.1:8787/health",
    "ollama": "http://127.0.0.1:11434/api/tags",
    "liteLLM": "http://127.0.0.1:4000/health/liveliness",
    "ada": "http://127.0.0.1:8085/health",
    "testingBay": "http://192.168.3.3:9311/health",
}

BACKEND_ENV_VARS = {
    "operatorKernel": "RCC_OPERATOR_KERNEL_HEALTH_URL",
    "bridge": "RCC_BRIDGE_HEALTH_URL",
    "ollama": "RCC_OLLAMA_HEALTH_URL",
    "liteLLM": "RCC_LITELLM_HEALTH_URL",
    "ada": "RCC_ADA_HEALTH_URL",
    "testingBay": "RCC_TESTING_BAY_HEALTH_URL",
}


def get_backend_targets() -> dict[str, str]:
    """Resolve probe URLs at call time so failures can be isolated safely."""
    return {
        name: os.getenv(BACKEND_ENV_VARS[name], default_url)
        for name, default_url in DEFAULT_BACKEND_TARGETS.items()
    }


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


def _gdbus(method: str, *args: str) -> dict:
    return run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.freedesktop.DBus",
            "--object-path",
            "/org/freedesktop/DBus",
            "--method",
            f"org.freedesktop.DBus.{method}",
            *args,
        ],
        timeout=3.0,
    )


def get_dbus_owner() -> dict:
    owner_result = _gdbus("GetNameOwner", APP_ID)
    if not owner_result.get("ok"):
        return {"owner": None, "pid": None, "error": owner_result.get("stderr") or owner_result.get("error")}

    owner_match = re.search(r"'([^']+)'", owner_result.get("stdout", ""))
    owner = owner_match.group(1) if owner_match else None
    if not owner:
        return {"owner": None, "pid": None, "error": "D-Bus owner response was not parseable"}

    pid_result = _gdbus("GetConnectionUnixProcessID", owner)
    pid_matches = re.findall(r"\b(\d+)\b", pid_result.get("stdout", "")) if pid_result.get("ok") else []
    pid = int(pid_matches[-1]) if pid_matches else None
    return {"owner": owner, "pid": pid, "error": None if pid else "D-Bus owner PID was not parseable"}


def get_process_identity(pid: int | None) -> dict:
    if not pid:
        return {"alive": False, "pid": None, "uid": None, "cwd": None, "executable": None, "argv": []}

    proc = Path("/proc") / str(pid)
    try:
        argv = (proc / "cmdline").read_bytes().split(b"\0")
        return {
            "alive": True,
            "pid": pid,
            "uid": proc.stat().st_uid,
            "cwd": str((proc / "cwd").resolve()),
            "executable": str((proc / "exe").resolve()),
            "argv": [part.decode("utf-8", errors="replace") for part in argv if part],
        }
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError) as exc:
        return {
            "alive": False,
            "pid": pid,
            "uid": None,
            "cwd": None,
            "executable": None,
            "argv": [],
            "error": str(exc),
        }


def get_process_source_commit(pid: int | None) -> str | None:
    """Read the immutable build stamp inherited by the running process."""
    if not pid:
        return None
    try:
        entries = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None
    prefix = b"RCC_SOURCE_COMMIT="
    for entry in entries:
        if entry.startswith(prefix):
            commit = entry[len(prefix) :].decode("ascii", errors="ignore").strip()
            return commit or None
    return None


def is_expected_primary(identity: dict) -> bool:
    executable = Path(identity.get("executable") or "").name
    argv = [str(part) for part in identity.get("argv") or []]
    return bool(
        identity.get("alive")
        and identity.get("uid") == os.getuid()
        and identity.get("cwd") == str(APP_ROOT)
        and executable.startswith("python3")
        and any(Path(part).name == "main.py" for part in argv)
    )


def get_visible_windows(pid: int | None) -> dict:
    if not pid:
        return {"probeAvailable": shutil.which("xdotool") is not None, "windows": []}
    if not shutil.which("xdotool"):
        return {"probeAvailable": False, "windows": [], "error": "xdotool is unavailable"}

    found = run(
        ["xdotool", "search", "--all", "--onlyvisible", "--pid", str(pid), "--name", "Roxy Command Center"],
        timeout=3.0,
    )
    window_ids = [line.strip() for line in found.get("stdout", "").splitlines() if line.strip().isdigit()]
    windows = []
    for window_id in window_ids:
        title_result = run(["xdotool", "getwindowname", window_id], timeout=2.0)
        geometry_result = run(["xdotool", "getwindowgeometry", "--shell", window_id], timeout=2.0)
        geometry_values = {}
        for line in geometry_result.get("stdout", "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                geometry_values[key] = value
        geometry = None
        if all(key in geometry_values for key in ("X", "Y", "WIDTH", "HEIGHT")):
            geometry = (
                f"{geometry_values['WIDTH']}x{geometry_values['HEIGHT']}"
                f"+{geometry_values['X']}+{geometry_values['Y']}"
            )
        windows.append(
            {
                "windowId": window_id,
                "title": title_result.get("stdout") or None,
                "geometry": geometry,
            }
        )
    return {"probeAvailable": True, "windows": windows}


def probe_backend(name: str, url: str, timeout: float = 1.5) -> tuple[str, dict]:
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return name, {"ok": 200 <= response.status < 400, "status": response.status, "url": url}
    except urllib.error.HTTPError as exc:
        return name, {"ok": False, "reachable": True, "status": exc.code, "url": url, "error": str(exc)}
    except Exception as exc:
        return name, {"ok": False, "reachable": False, "status": None, "url": url, "error": str(exc)}


def get_backend_statuses() -> dict:
    targets = get_backend_targets()
    with ThreadPoolExecutor(max_workers=len(targets)) as executor:
        rows = executor.map(lambda item: probe_backend(*item), targets.items())
        return dict(rows)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def get_last_traceback() -> dict | None:
    for path in (RUNTIME_DIR / "run.log", RUNTIME_DIR / "fault.log"):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        marker = text.rfind("Traceback (most recent call last):")
        if marker == -1:
            continue
        excerpt = text[marker : marker + 4000].strip()
        return {"path": str(path), "excerpt": excerpt}
    return None


def get_source_commit() -> str | None:
    result = run(["git", "rev-parse", "HEAD"], timeout=3.0)
    return result.get("stdout") if result.get("ok") else None


def classify_native_health(report: dict) -> str:
    if not report.get("processAlive"):
        return "RCC_STARTUP_EXCEPTION" if report.get("lastTraceback") else "RCC_PROCESS_MISSING"
    if not report.get("primaryIdentityValid"):
        return "RCC_PRIMARY_IDENTITY_MISMATCH"
    if not report.get("windowProbeAvailable"):
        return "RCC_WINDOW_PROBE_UNAVAILABLE"
    count = report.get("visibleWindowCount", 0)
    if count == 0:
        return "RCC_STALE_PRIMARY_NO_WINDOW"
    if count > 1:
        return "RCC_MULTIPLE_WINDOWS"
    if not report.get("sourceCommitVerified"):
        return "RCC_BUILD_PROVENANCE_MISSING"
    if report.get("sourceAligned") is False:
        return "RCC_BUILD_SOURCE_DRIFT"
    if any(not status.get("ok") for status in report.get("backendStatuses", {}).values()):
        return "RCC_BACKEND_DEGRADED"
    return "RCC_NATIVE_HEALTHY"


def native_health_report(include_backends: bool = True) -> dict:
    dbus = get_dbus_owner()
    identity = get_process_identity(dbus.get("pid"))
    window_probe = get_visible_windows(dbus.get("pid"))
    windows = window_probe["windows"]
    process_source_commit = get_process_source_commit(dbus.get("pid"))
    working_tree_commit = get_source_commit()
    report = {
        "schemaVersion": "rcc-native-health.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "processAlive": identity.get("alive", False),
        "dbusOwner": dbus.get("owner"),
        "dbusOwnerPid": dbus.get("pid"),
        "primaryIdentityValid": is_expected_primary(identity),
        "process": identity,
        "windowProbeAvailable": window_probe["probeAvailable"],
        "visibleWindowCount": len(windows),
        "windows": windows,
        "windowTitle": windows[0].get("title") if len(windows) == 1 else None,
        "windowGeometry": windows[0].get("geometry") if len(windows) == 1 else None,
        "launcherPath": str(LAUNCHER_PATH),
        "sourceCommit": process_source_commit,
        "sourceCommitVerified": process_source_commit is not None,
        "sourceCommitSource": "process-environment" if process_source_commit else None,
        "workingTreeCommit": working_tree_commit,
        "sourceAligned": (
            process_source_commit == working_tree_commit
            if process_source_commit and working_tree_commit
            else None
        ),
        "backendStatuses": get_backend_statuses() if include_backends else {},
        "lastLaunchExit": _read_json(RUNTIME_DIR / "last_exit.json"),
        "lastTraceback": get_last_traceback(),
    }
    report["status"] = classify_native_health(report)
    report["ok"] = report["status"] in {"RCC_NATIVE_HEALTHY", "RCC_BACKEND_DEGRADED"}
    return report


def activate_primary() -> dict:
    return run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            APP_ID,
            "--object-path",
            APP_OBJECT_PATH,
            "--method",
            "org.gtk.Application.Activate",
            "{}",
        ],
        timeout=3.0,
    )


def write_launch_receipt(payload: dict) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = RECEIPT_DIR / f"rcc-launch-{stamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
    return path


def terminate_exact_primary(pid: int, timeout: float = 5.0) -> dict:
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not (Path("/proc") / str(pid)).exists():
            return {"terminated": True, "signal": "SIGTERM"}
        time.sleep(0.1)

    os.kill(pid, signal.SIGKILL)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not (Path("/proc") / str(pid)).exists():
            return {"terminated": True, "signal": "SIGKILL"}
        time.sleep(0.1)
    return {"terminated": False, "signal": "SIGKILL", "error": "process remained alive"}


def prepare_launch() -> tuple[dict, int]:
    health = native_health_report(include_backends=False)
    launch_source_commit = health.get("sourceCommit") or health.get("workingTreeCommit")
    base_receipt = {
        "schemaVersion": "rcc-native-launch-receipt.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "launcherPath": str(LAUNCHER_PATH),
        "sourceCommit": launch_source_commit,
        "sourceCommitSource": (
            health.get("sourceCommitSource")
            if health.get("sourceCommit")
            else "working-tree-launch-target"
        ),
        "observed": health,
    }

    if not health["processAlive"]:
        base_receipt.update({"status": "RCC_PROCESS_MISSING", "outcome": "START_REQUIRED"})
        path = write_launch_receipt(base_receipt)
        return {**base_receipt, "receiptPath": str(path)}, 0

    if not health["primaryIdentityValid"]:
        base_receipt.update({"status": "RCC_PRIMARY_IDENTITY_MISMATCH", "outcome": "REFUSED"})
        path = write_launch_receipt(base_receipt)
        return {**base_receipt, "receiptPath": str(path)}, 2

    if not health["windowProbeAvailable"]:
        base_receipt.update({"status": "RCC_WINDOW_PROBE_UNAVAILABLE", "outcome": "REFUSED"})
        path = write_launch_receipt(base_receipt)
        return {**base_receipt, "receiptPath": str(path)}, 3

    if health["visibleWindowCount"] == 1:
        activation = activate_primary()
        if not activation.get("ok"):
            base_receipt.update(
                {
                    "status": "RCC_ACTIVATION_FAILED",
                    "outcome": "REFUSED",
                    "activation": activation,
                }
            )
            path = write_launch_receipt(base_receipt)
            return {**base_receipt, "receiptPath": str(path)}, 6
        base_receipt.update(
            {
                "status": "RCC_NATIVE_HEALTHY",
                "outcome": "EXISTING_PRIMARY_PRESENTED",
                "activation": activation,
            }
        )
        path = write_launch_receipt(base_receipt)
        return {**base_receipt, "receiptPath": str(path)}, 10

    if health["visibleWindowCount"] > 1:
        base_receipt.update({"status": "RCC_MULTIPLE_WINDOWS", "outcome": "REFUSED"})
        path = write_launch_receipt(base_receipt)
        return {**base_receipt, "receiptPath": str(path)}, 4

    base_receipt.update(
        {
            "status": "RCC_STALE_PRIMARY_NO_WINDOW",
            "outcome": "TERMINATION_PENDING",
            "reason": "D-Bus primary owns org.roxy.CommandCenter but has no visible native window",
        }
    )
    receipt_path = write_launch_receipt(base_receipt)
    termination = terminate_exact_primary(health["dbusOwnerPid"])
    base_receipt["termination"] = termination
    base_receipt["outcome"] = "RECOVERED_START_REQUIRED" if termination["terminated"] else "TERMINATION_FAILED"
    receipt_path.write_text(json.dumps(base_receipt, indent=2, sort_keys=True) + "\n")
    return {**base_receipt, "receiptPath": str(receipt_path)}, 0 if termination["terminated"] else 5


def dependency_report() -> tuple[dict, int]:
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

    return report, 0 if report["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("dependencies", "native-health", "prepare-launch"),
        default="dependencies",
    )
    parser.add_argument("--no-backends", action="store_true")
    args = parser.parse_args()

    if args.mode == "native-health":
        report = native_health_report(include_backends=not args.no_backends)
        code = 0 if report["ok"] else 1
    elif args.mode == "prepare-launch":
        report, code = prepare_launch()
    else:
        report, code = dependency_report()

    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
