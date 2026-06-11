"""
Read-only Roxy status provider.

No mutation.
No systemctl start/stop.
No mount/remount.
No deletes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


PROVIDER_VERSION = "phase2c-mos-observability-v1"
RECOVERY_ROOT = Path("/mnt/work/roxy-core/recovered/value-extraction-20260517-074413")
MOS_ROOT = Path("/mnt/work/testing-bay/mindsong-juke-hub-x64")
OPERATOR_PACK_ROOT = RECOVERY_ROOT / "100-codex-operator-pack"
GUI_PROOF_ROOT = RECOVERY_ROOT / "110-roxy-gui-proof-pack"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def _run(cmd: list[str], timeout: int = 5) -> dict[str, Any]:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stdout": "", "stderr": ""}


def _findmnt(path: str) -> dict[str, Any]:
    source = _run(["findmnt", "-no", "SOURCE", path])
    fstype = _run(["findmnt", "-no", "FSTYPE", path])
    options = _run(["findmnt", "-no", "OPTIONS", path])
    opts = options.get("stdout", "")
    return {
        "mounted": bool(source.get("stdout")),
        "source": source.get("stdout", ""),
        "fstype": fstype.get("stdout", ""),
        "options": opts,
        "readonly": f",{opts},".find(",ro,") >= 0,
    }


def mount_status() -> dict[str, Any]:
    mounts = {
        "lacie_orico_archive": "/media/mark/ROXY_ORICO_ARCHI",
        "p51_source_vault": "/media/mark/P51_GDRIVE_CLONE",
        "orico_live_root": "/media/mark/63e50236-2a2a-414f-a4fd-96591b2c931e",
    }
    return {name: {"path": path, **_findmnt(path)} for name, path in mounts.items()}


def proof_status() -> dict[str, Any]:
    urls = {
        "studio_app_19135": "http://127.0.0.1:19135/__observatory/source-fingerprint?fresh=1",
        "studio_api_19310": "http://127.0.0.1:19310/health",
        "roxy_api_9311": "http://192.168.3.3:9311/health",
    }
    out: dict[str, Any] = {}
    for name, url in urls.items():
        result = _run(["curl", "-fsS", "-m", "5", url])
        out[name] = {"ok": result["ok"], "url": url, "sample": result["stdout"][:300]}

    thunderbolt = _run(["ip", "-br", "addr", "show", "thunderbolt0"])
    route = _run(["ip", "route", "get", "192.168.3.1"])
    out["thunderbolt0"] = {
        "ok": "192.168.3.3" in thunderbolt.get("stdout", ""),
        "address": thunderbolt.get("stdout", ""),
        "route": route.get("stdout", ""),
    }
    return out


def gpu_status() -> dict[str, Any]:
    lspci = _run(
        ["bash", "-lc", "lspci -nn | grep -Ei 'vga|3d|display|amd|radeon|navi|nvidia' || true"]
    )
    vulkan = _run(
        ["bash", "-lc", "vulkaninfo --summary 2>/dev/null | grep -E 'GPU[0-9]|deviceName|RADV|llvmpipe' || true"]
    )
    benchmark = Path("/home/mark/roxy-health/6900-savage-benchmark-20260516-180750/99-100-metric-report.md")
    verdict = ""
    if benchmark.exists():
        text = benchmark.read_text(errors="replace")
        for line in text.splitlines():
            if "Final classification" in line or "Sub-classification" in line:
                verdict += line.strip() + "\n"
    return {
        "lspci": lspci["stdout"],
        "vulkan": vulkan["stdout"],
        "benchmark_report": str(benchmark),
        "benchmark_report_exists": benchmark.exists(),
        "benchmark_verdict": verdict.strip(),
        "webgpu_max_status": "unstable_on_navi21",
        "safe_lane_status": "pass_with_navi21_selected",
    }


def storage_identity() -> dict[str, Any]:
    return {
        "lsblk": _run(
            ["lsblk", "-o", "NAME,PATH,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL"],
            timeout=10,
        )["stdout"]
    }


def recovery_reports() -> dict[str, Any]:
    reports = [
        RECOVERY_ROOT / "10-reports/PHASE0_STATE.md",
        RECOVERY_ROOT / "10-reports/PHASE1_CANDIDATE_INDEX.md",
        RECOVERY_ROOT / "10-reports/PHASE1_REVIEW_PACKET.md",
        RECOVERY_ROOT / "10-reports/PHASE2A_REVIEW_STAGING_REPORT.md",
        RECOVERY_ROOT / "30-phase2b-roxy-doctor/reports/PHASE2B_ROXY_DOCTOR_AND_CC_REVIEW_REPORT.md",
        RECOVERY_ROOT / "30-phase2b-roxy-doctor/reports/ROXY_DOCTOR_PROTOTYPE_OUTPUT.txt",
    ]
    return {str(path): path.exists() for path in reports}


def _latest_file_under(root: Path, pattern: str) -> dict[str, Any]:
    """Find newest artifact inside an approved root. Never glob from /."""
    try:
        candidates = sorted(root.glob(pattern), key=lambda path: path.stat().st_mtime)
    except Exception:
        candidates = []
    if not candidates:
        return {"exists": False, "path": ""}
    latest = candidates[-1]
    return {
        "exists": True,
        "path": str(latest),
        "mtime": latest.stat().st_mtime,
        "size": latest.stat().st_size,
    }


def _http_json(url: str, timeout: int = 2) -> dict[str, Any]:
    result = _run(["curl", "-fsS", "-m", str(timeout), url], timeout=timeout + 1)
    parsed: dict[str, Any] = {}
    if result.get("ok") and result.get("stdout"):
        try:
            parsed = json.loads(result["stdout"])
        except Exception:
            parsed = {"sample": result["stdout"][:300]}
    return {
        "ok": result.get("ok", False),
        "url": url,
        "returncode": result.get("returncode"),
        "error": result.get("stderr") or result.get("error", ""),
        "data": parsed,
    }


def proof_browser_status() -> dict[str, Any]:
    """Helper-only CDP probe of Testing Bay formal-CDP port (9460).

    Returns target count, current visible page(s), and teacher-studio tab count.
    This is a helper reading; final browser truth still requires live CDP.
    """
    cdp_url = "http://127.0.0.1:9460/json/list"
    result = _http_json(cdp_url, timeout=3)
    targets = result.get("data") or []
    if not isinstance(targets, list):
        targets = []

    pages = [t for t in targets if t.get("type") == "page"]
    current_url = pages[0].get("url", "") if pages else ""
    current_title = pages[0].get("title", "") if pages else ""
    teacher_studio_tabs = [
        t for t in pages
        if "teacher-studio" in (t.get("url", "") + t.get("title", "")).lower()
    ]

    return {
        "ok": result.get("ok", False) and len(targets) > 0,
        "port": 9460,
        "target_count": len(targets),
        "page_count": len(pages),
        "current_url": current_url,
        "current_title": current_title,
        "teacher_studio_tabs": len(teacher_studio_tabs),
        "error": result.get("error", ""),
        "note": "HELPER_ONLY_NOT_FINAL_TRUTH",
    }


def mos_control_plane_status() -> dict[str, Any]:
    latest_boot = _latest_file_under(
        MOS_ROOT / ".autonomous/test-evidence/hardware-control",
        "boot-proof-*.json",
    )
    latest_boot_data = _read_json(Path(latest_boot["path"])) if latest_boot.get("exists") else {}

    ingress = _http_json("http://127.0.0.1:49172/healthz")
    authority = _http_json("http://127.0.0.1:49173/healthz")
    listeners = _run(
        [
            "bash",
            "-lc",
            "ss -ltnp | grep -E ':49170|:49172|:49173|:9135|:19135' || true",
        ]
    )
    inventory_path = MOS_ROOT / "tools/hardware-device-inventory.json"
    inventory = _read_json(inventory_path) if inventory_path.exists() else {"ok": False, "error": "missing"}
    profiles_source = MOS_ROOT / "src/store/directorBindingsStore.ts"

    return {
        "repo": str(MOS_ROOT),
        "ingress_health": ingress,
        "authority_health": authority,
        "listeners": listeners.get("stdout", ""),
        "latest_boot_proof": latest_boot,
        "latest_boot_summary": {
            "passed": latest_boot_data.get("passed"),
            "failed": latest_boot_data.get("failed"),
            "tests": len(latest_boot_data.get("tests", [])) if isinstance(latest_boot_data.get("tests"), list) else None,
            "startedAt": latest_boot_data.get("startedAt"),
            "finishedAt": latest_boot_data.get("finishedAt"),
        },
        "inventory": {
            "path": str(inventory_path),
            "exists": inventory_path.exists(),
            "devices": len(inventory.get("devices", [])) if isinstance(inventory.get("devices"), list) else None,
            "lastUpdated": inventory.get("lastUpdated"),
        },
        "profiles_source": {
            "path": str(profiles_source),
            "exists": profiles_source.exists(),
        },
        "canonical_routes": {
            "input": "/api/input-event",
            "alias": "/api/control/input",
            "stream": "ws://127.0.0.1:49172/stream",
        },
        "note": "Read-only status only. UI must not own the MOS authority.",
    }


def status_tier(
    *,
    usb_present: bool = False,
    by_id_present: bool = False,
    dry_run_proven: bool = False,
    synthetic_route_proven: bool = False,
    live_capture_proven: bool = False,
    routed_proven: bool = False,
    operator_ready: bool = False,
    planned: bool = False,
    unproven: bool = False,
) -> str:
    if unproven:
        return "unproven"
    if operator_ready:
        return "operator-ready"
    if routed_proven:
        return "routed-proven"
    if live_capture_proven:
        return "live-capture-proven"
    if synthetic_route_proven:
        return "synthetic-route-proven"
    if dry_run_proven:
        return "dry-run-proven"
    if usb_present or by_id_present:
        return "verified-present"
    if planned:
        return "planned"
    return "unseen"


def device_status(
    *,
    usb_id: str | None = None,
    usb_present: bool = False,
    by_id_present: bool = False,
    dry_run_proven: bool = False,
    synthetic_route_proven: bool = False,
    live_capture_ready: bool = False,
    live_capture_proven: bool = False,
    routed_proven: bool = False,
    operator_ready: bool = False,
    planned: bool = False,
    unproven: bool = False,
    path: str = "",
    note: str = "",
) -> dict[str, Any]:
    return {
        "usbId": usb_id,
        "usbPresent": usb_present,
        "byIdPresent": by_id_present,
        "dryRunProven": dry_run_proven,
        "syntheticRouteProven": synthetic_route_proven,
        "liveCaptureReady": live_capture_ready,
        "liveCaptureProven": live_capture_proven,
        "routedProven": routed_proven,
        "operatorReady": operator_ready,
        "statusTier": status_tier(
            usb_present=usb_present,
            by_id_present=by_id_present,
            dry_run_proven=dry_run_proven,
            synthetic_route_proven=synthetic_route_proven,
            live_capture_proven=live_capture_proven,
            routed_proven=routed_proven,
            operator_ready=operator_ready,
            planned=planned,
            unproven=unproven,
        ),
        "path": path,
        "note": note,
    }


def control_surface_status() -> dict[str, Any]:
    lsusb = _run(["lsusb"])
    by_id = _run(["bash", "-lc", "find /dev/input/by-id -maxdepth 1 -type l -printf '%f -> %l\\n' | sort || true"])
    pydeps = _run(
        [
            "python3",
            "-c",
            (
                "import importlib.util,json;"
                "mods=['evdev','requests','websocket','websockets'];"
                "print(json.dumps({m: importlib.util.find_spec(m) is not None for m in mods}))"
            ),
        ]
    )
    deps: dict[str, bool] = {}
    try:
        deps = json.loads(pydeps.get("stdout", "{}"))
    except Exception:
        deps = {}

    lsusb_text = lsusb.get("stdout", "")
    by_id_text = by_id.get("stdout", "")
    evdev_ready = bool(deps.get("evdev"))
    g502_usb = "046d:c08b" in lsusb_text
    g502_by_id = "Logitech_G502_HERO" in by_id_text
    evision_usb = "320f:5000" in lsusb_text
    evision_by_id = "Evision_RGB_Keyboard" in by_id_text
    redragon_visible = (
        "redragon" in lsusb_text.lower()
        or "red dragon" in lsusb_text.lower()
        or "redragon" in by_id_text.lower()
        or "red dragon" in by_id_text.lower()
    )
    return {
        "devices": {
            "logitech-g502-hero": device_status(
                usb_id="046d:c08b",
                usb_present=g502_usb,
                by_id_present=g502_by_id,
                dry_run_proven=g502_usb and g502_by_id,
                live_capture_ready=evdev_ready,
                note="verified-present + dry-run-proven; live capture pending python evdev and real event capture",
            ),
            "evision-rgb-keyboard": device_status(
                usb_id="320f:5000",
                usb_present=evision_usb,
                by_id_present=evision_by_id,
                dry_run_proven=evision_usb and evision_by_id,
                live_capture_ready=evdev_ready,
                note="verified-present + dry-run-proven; live capture pending python evdev and real event capture",
            ),
            "redragon": device_status(
                usb_present=redragon_visible,
                by_id_present=redragon_visible,
                live_capture_ready=evdev_ready,
                unproven=not redragon_visible,
                note="unproven until USB VID:PID and by-id evidence exist",
            ),
            "stream-deck": device_status(
                synthetic_route_proven=True,
                path="CompanionInputDriver",
                note="synthetic parser/route proof only; real Companion payload pending",
            ),
            "loupedeck": device_status(
                synthetic_route_proven=True,
                path="CompanionInputDriver",
                note="synthetic parser/route proof only; real Companion rotary/press/release pending",
            ),
            "touchportal": device_status(
                synthetic_route_proven=True,
                path="HTTP shortcut",
                note="HTTP shortcut route proven synthetically; page/export proof pending",
            ),
            "softstep-midi": device_status(
                planned=True,
                path="MIDI services",
                note="profile/path present; no live hardware proof in this panel",
            ),
            "s22-ipad": device_status(
                planned=True,
                path="existing operator/lifepanel surfaces",
                note="planned contract normalization; no runtime emission proof in this panel",
            ),
        },
        "python": deps,
        "evdev_live_capture_ready": evdev_ready,
        "raw": {
            "lsusb": "\n".join(
                line for line in lsusb_text.splitlines()
                if any(token in line.lower() for token in ["046d:c08b", "320f:5000", "logitech", "evision", "redragon", "red dragon", "elgato", "loupedeck"])
            ),
            "by_id": by_id_text,
        },
        "note": "G502/Evision are verified-present plus dry-run-proven. Redragon remains unproven until USB/by-id proof exists.",
    }


def skybeam_status() -> dict[str, Any]:
    skybeam_root = MOS_ROOT / "tools/skybeam-command-center"
    output_root = skybeam_root / "output"
    latest_recording = _latest_file_under(output_root, "skybeam-*/skybeam-recording.mp4")
    latest_meta = _latest_file_under(output_root, "skybeam-*/meta.json")
    obs_probe = _run(
        [
            "bash",
            "-lc",
            "ss -ltnp | grep -E ':4455|:5960|:5961|:5962' || true",
        ]
    )
    return {
        "root": str(skybeam_root),
        "exists": skybeam_root.exists(),
        "latest_recording": latest_recording,
        "latest_meta": latest_meta,
        "obs_listener_probe": obs_probe.get("stdout", ""),
        "event_policy": {
            "status": "planned-status-only",
            "deviceId": "skybeam-command-center",
            "sourceType": "ws-bridge",
            "deviceClass": "network-bridge",
            "transport": "ws",
            "route": "/api/input-event",
        },
        "note": "Skybeam is status/proof surface only here; no Skybeam bus or scene router.",
    }


def operator_pack_status() -> dict[str, Any]:
    latest_visual_log = _latest_file_under(OPERATOR_PACK_ROOT / "evidence", "visual-proof-*/visual-proof.log")
    latest_screenshot = _latest_file_under(OPERATOR_PACK_ROOT / "evidence", "visual-proof-*/screenshot.png")
    latest_report = _latest_file_under(OPERATOR_PACK_ROOT / "reports", "operator-pack-report-*.md")
    latest_gui_proof = _latest_file_under(GUI_PROOF_ROOT / "reports", "command-center-proof-*.md")
    return {
        "operator_pack_root": str(OPERATOR_PACK_ROOT),
        "gui_proof_root": str(GUI_PROOF_ROOT),
        "installed_commands": {
            name: _run(["bash", "-lc", f"command -v {name} || true"]).get("stdout", "")
            for name in [
                "roxy-agent-preflight",
                "roxy-agent-certify",
                "roxy-agent-visual-proof",
                "roxy-agent-perf-proof",
                "roxy-agent-report",
                "roxy-doctor",
            ]
        },
        "latest_visual_log": latest_visual_log,
        "latest_screenshot": latest_screenshot,
        "latest_report": latest_report,
        "latest_command_center_proof": latest_gui_proof,
    }


def snapshot() -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "providerVersion": PROVIDER_VERSION,
        "host": _run(["hostname"])["stdout"],
        "proof": proof_status(),
        "mounts": mount_status(),
        "storage": storage_identity(),
        "gpu": gpu_status(),
        "recovery_reports": recovery_reports(),
        "operator_pack": operator_pack_status(),
        "mos_control_plane": mos_control_plane_status(),
        "control_surfaces": control_surface_status(),
        "skybeam": skybeam_status(),
        "warnings": [
            "Read-only provider only.",
            "Roxy Command Center is an observability shell, not authority.",
            "Do not enable old systemd units.",
            "Do not use old GPU high-power rules as defaults.",
            "Do not remount ORICO/P51/LaCie read-write.",
            "Do not treat WebGPU-max on NAVI21 as stable.",
            "Do not claim Redragon until USB/by-id proof exists.",
            "Do not claim live evdev capture until python evdev is installed and a real event is captured.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2))
