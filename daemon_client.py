#!/usr/bin/env python3
"""
Async daemon client with timeout handling.
ROXY-CMD-STORY-001: Non-blocking HTTP fetches with GLib integration.
"""

import subprocess
import json
import os
import threading
import time
import urllib.request
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib

# Lazy import to avoid GTK init issues during import
def _get_gpu_monitor():
    from services.gpu_monitor import get_gpu_monitor
    return get_gpu_monitor()

DAEMON_PATH = Path.home() / ".config/eww/roxy-panel/scripts/roxy-panel-daemon.py"
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_TIMEOUT = 2.0  # 2 second timeout per ORACLE-04 mitigation
MAX_CACHE_AGE = 30.0   # Cache TTL in seconds

@dataclass
class DaemonResponse:
    """Container for daemon response with metadata."""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    source: str = "unknown"
    error: Optional[str] = None
    is_stale: bool = False

class DaemonClient:
    """
    Async daemon client with caching and GLib integration.
    
    Features:
    - Thread pool for non-blocking HTTP fetches
    - 2s timeout to prevent UI freeze (ORACLE-04)
    - Response caching with staleness indicator
    - GLib.idle_add for safe UI updates
    """
    
    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="daemon")
        self._cache: Optional[DaemonResponse] = None
        self._probe_cache: Dict[str, Tuple[float, Any]] = {}
        self._pending = False
        self._callbacks: list = []
        
        # Mode configuration
        self.mode = "auto"
        self.remote_host = "10.0.0.69"
        self.remote_port = 8766

    def _cached(self, key: str, ttl: float, producer: Callable[[], Any]) -> Any:
        """Return a cached probe result when it is still fresh."""
        now = time.time()
        cached = self._probe_cache.get(key)
        if cached and now - cached[0] <= ttl:
            return cached[1]
        value = producer()
        self._probe_cache[key] = (now, value)
        return value
    
    def configure(self, mode: str = "auto", remote_host: str = "10.0.0.69", remote_port: int = 8766):
        """Update daemon connection configuration."""
        self.mode = mode
        self.remote_host = remote_host
        self.remote_port = remote_port
    
    def get_cached(self) -> Optional[DaemonResponse]:
        """Get cached response if available and fresh."""
        if self._cache is None:
            return None
        
        age = time.time() - self._cache.timestamp
        if age > MAX_CACHE_AGE:
            self._cache.is_stale = True
        
        return self._cache
    
    def fetch_async(self, callback: Callable[[DaemonResponse], None]):
        """
        Fetch daemon status asynchronously.
        
        Callback will be invoked on main thread via GLib.idle_add.
        If a fetch is already pending, callback is queued.
        """
        self._callbacks.append(callback)
        
        if self._pending:
            return  # Already fetching, callback will be called when complete
        
        self._pending = True
        self.executor.submit(self._fetch_worker)
    
    def _fetch_worker(self):
        """Worker thread: fetch from daemon and schedule callback."""
        response = self._do_fetch()
        
        # Cache the response
        self._cache = response
        
        # Schedule UI update on main thread
        GLib.idle_add(self._deliver_callbacks, response)
    
    def _deliver_callbacks(self, response: DaemonResponse) -> bool:
        """Deliver response to all waiting callbacks (main thread)."""
        self._pending = False
        callbacks = self._callbacks[:]
        self._callbacks.clear()
        
        for cb in callbacks:
            try:
                cb(response)
            except Exception as e:
                print(f"[DaemonClient] Callback error: {e}")
        
        return False  # Don't repeat
    
    def _do_fetch(self) -> DaemonResponse:
        """Synchronous fetch (runs in worker thread)."""
        env = os.environ.copy()
        env.update({
            "ROXY_MODE": self.mode,
            "ROXY_REMOTE_HOST": self.remote_host,
            "ROXY_REMOTE_PORT": str(self.remote_port),
        })

        if not DAEMON_PATH.exists():
            return DaemonResponse(
                data=self._local_roxy_snapshot(),
                timestamp=time.time(),
                source="local-roxy-adapt"
            )
        
        try:
            result = subprocess.run(
                ["python3", str(DAEMON_PATH), "--mode", "oneshot"],
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return DaemonResponse(
                    data=self._local_roxy_snapshot(error=f"Daemon exit code {result.returncode}: {result.stderr}"),
                    timestamp=time.time(),
                    source="local-roxy-adapt"
                )
            
            data = json.loads(result.stdout)
            return DaemonResponse(
                data=data,
                timestamp=time.time(),
                source=data.get("source", "unknown")
            )
        
        except subprocess.TimeoutExpired:
            return DaemonResponse(
                error=f"Daemon timeout ({self.timeout}s)",
                timestamp=time.time(),
                source="timeout"
            )
        except json.JSONDecodeError as e:
            return DaemonResponse(
                error=f"JSON parse error: {e}",
                timestamp=time.time(),
                source="parse_error"
            )
        except Exception as e:
            return DaemonResponse(
                data=self._local_roxy_snapshot(error=f"Daemon call failed: {e}"),
                timestamp=time.time(),
                source="local-roxy-adapt"
            )

    def _run_text(self, command: list[str], timeout: float = 2.0) -> tuple[bool, str]:
        """Run a read-only command and return success/output."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = (result.stdout or result.stderr or "").strip()
            return result.returncode == 0, output
        except Exception as exc:
            return False, str(exc)

    def _run_text_cached(self, command: list[str], timeout: float = 2.0, ttl: float = 15.0) -> tuple[bool, str]:
        key = "cmd:" + "\0".join(command)
        return self._cached(key, ttl, lambda: self._run_text(command, timeout=timeout))

    def _failed_unit_count(self) -> int:
        ok, output = self._run_text_cached(["systemctl", "--failed", "--no-legend", "--no-pager"], timeout=3.0, ttl=30.0)
        if not ok or not output:
            return 0
        return len([line for line in output.splitlines() if line.strip()])

    def _load_info(self) -> dict:
        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as fh:
                parts = fh.read().split()
            return {
                "load_1m": float(parts[0]),
                "load_5m": float(parts[1]),
                "load_15m": float(parts[2]),
                "logical_cpus": os.cpu_count() or 1,
            }
        except Exception:
            return {"load_1m": 0.0, "load_5m": 0.0, "load_15m": 0.0, "logical_cpus": os.cpu_count() or 1}

    def _cpu_idle_pct(self) -> float:
        def read_cpu() -> tuple[int, int]:
            with open("/proc/stat", "r", encoding="utf-8") as fh:
                fields = [int(x) for x in fh.readline().split()[1:]]
            idle = fields[3] + fields[4]
            total = sum(fields)
            return idle, total

        try:
            idle1, total1 = read_cpu()
            time.sleep(0.15)
            idle2, total2 = read_cpu()
            total_delta = max(total2 - total1, 1)
            idle_delta = idle2 - idle1
            return max(0.0, min(100.0, idle_delta / total_delta * 100.0))
        except Exception:
            return 0.0

    def _memory_info(self) -> dict:
        values = {}
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as fh:
                for line in fh:
                    key, raw = line.split(":", 1)
                    values[key] = int(raw.strip().split()[0]) * 1024
        except Exception:
            return {"mem_used_gb": 0.0, "mem_total_gb": 0.0, "mem_available_gb": 0.0}

        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        used = max(total - available, 0)
        gib = 1024**3
        return {
            "mem_used_gb": used / gib,
            "mem_total_gb": total / gib,
            "mem_available_gb": available / gib,
        }

    def _usage_for_path(self, path: str) -> dict:
        try:
            usage = shutil.disk_usage(path)
            used_pct = usage.used / usage.total * 100 if usage.total else 0.0
            return {
                "mount": path,
                "total_gb": usage.total / (1024**3),
                "used_gb": usage.used / (1024**3),
                "free_gb": usage.free / (1024**3),
                "used_pct": used_pct,
            }
        except Exception as exc:
            return {"mount": path, "error": str(exc), "used_pct": 0.0}

    def _temperature_summary(self) -> dict:
        return self._cached("temperature_summary", 10.0, self._temperature_summary_uncached)

    def _temperature_summary_uncached(self) -> dict:
        temps: dict[str, float] = {}
        for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
            try:
                name = (hwmon / "name").read_text().strip()
            except Exception:
                continue
            values = []
            for temp_input in hwmon.glob("temp*_input"):
                try:
                    values.append(int(temp_input.read_text().strip()) / 1000.0)
                except Exception:
                    pass
            if values:
                key = name
                if key in temps:
                    key = f"{name}-{hwmon.name}"
                temps[key] = max(values)

        cpu = temps.get("coretemp", 0.0)
        nvme = max((value for key, value in temps.items() if key.startswith("nvme")), default=0.0)
        gpu = max((value for key, value in temps.items() if key.startswith("amdgpu")), default=0.0)
        hottest = max(temps.values(), default=0.0)
        return {
            "cpu_c": cpu,
            "nvme_max_c": nvme,
            "gpu_max_c": gpu,
            "hottest_c": hottest,
            "status": "cool" if hottest < 65 else "warm" if hottest < 80 else "hot",
        }

    def _external_state(self) -> dict:
        findmnt_ok, mounted = self._run_text_cached(["findmnt", "-rn"], timeout=3.0, ttl=30.0)
        text = mounted if findmnt_ok else ""
        return {
            "p51_visible": "P51_GDRIVE_CLONE" in text,
            "roxy_safety_mounted": "ROXY_SAFETY" in text,
            "mx_live_mounted": "MX-Live" in text,
        }

    def _active_workloads(self) -> dict:
        return self._cached("active_workloads", 15.0, self._active_workloads_uncached)

    def _active_workloads_uncached(self) -> dict:
        ollama_ok, ollama_ps = self._run_text(["ollama", "ps"], timeout=3.0)
        docker_ok, docker_ps = self._run_text(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            timeout=3.0,
        )
        ollama_count = max(len([line for line in ollama_ps.splitlines()[1:] if line.strip()]), 0) if ollama_ok else 0
        docker_count = len([line for line in docker_ps.splitlines() if line.strip()]) if docker_ok else 0
        return {
            "ollama_active_count": ollama_count,
            "docker_container_count": docker_count,
        }

    def _service_state(self, service: str) -> dict:
        return self._cached(f"service_state:{service}", 15.0, lambda: self._service_state_uncached(service))

    def _service_state_uncached(self, service: str) -> dict:
        active_ok, active = self._run_text(["systemctl", "is-active", service])
        enabled_ok, enabled = self._run_text(["systemctl", "is-enabled", service])
        return {
            "display_name": service,
            "active": active_ok,
            "health": "ok" if active_ok else "unhealthy",
            "active_state": active,
            "enabled": enabled if enabled_ok else "unknown",
        }

    def _ollama_models(self) -> tuple[bool, list[dict], str]:
        return self._cached("ollama_models", 30.0, self._ollama_models_uncached)

    def _ollama_models_uncached(self) -> tuple[bool, list[dict], str]:
        try:
            with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2.0) as resp:
                payload = json.loads(resp.read().decode())
            models = []
            for item in payload.get("models", []):
                models.append({
                    "name": item.get("name", "unknown"),
                    "size": item.get("size", 0),
                    "vram_gb": 0,
                })
            return True, models, ""
        except Exception as exc:
            return False, [], str(exc)

    def _read_apex_status_json(self) -> Optional[dict]:
        """Read canonical ~/.roxy/apex-status.json if available."""
        try:
            path = Path.home() / ".roxy" / "apex-status.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[daemon_client] apex-status.json read failed: {e}")
        return None

    def _qdrant_info(self) -> dict:
        """Query Qdrant for live vector store stats."""
        return self._cached("qdrant_info", 30.0, self._qdrant_info_uncached)

    def _qdrant_info_uncached(self) -> dict:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:3002/collections/mindsong-brain-v1",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                payload = json.loads(resp.read().decode())
            result = payload.get("result", {})
            return {
                "status": result.get("status", "unknown"),
                "points_count": result.get("points_count", 0),
                "indexed_vectors_count": result.get("indexed_vectors_count", 0),
                "vectors_count": result.get("vectors_count", 0),
                "reachable": True,
            }
        except Exception as e:
            return {"reachable": False, "error": str(e)[:120]}

    def _proxy_health(self) -> dict:
        """Query roxy-chat-proxy health without triggering model generation."""
        return self._cached("proxy_health", 15.0, self._proxy_health_uncached)

    def _proxy_health_uncached(self) -> dict:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:4001/health",
                headers={"Content-Type": "application/json"},
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                payload = json.loads(resp.read().decode())
            t1 = time.time()
            return {
                "reachable": True,
                "health_latency_ms": round((t1 - t0) * 1000),
                "upstream_reachable": payload.get("upstreamReachable", False),
                "prompt_loaded": payload.get("promptLoaded", False),
                "skill_docs": payload.get("skillDocs", 0),
                "skill_embeddings_loaded": payload.get("skillEmbeddingsLoaded", False),
                "storage": payload.get("storage", {}),
                "max_tokens_floor": payload.get("maxTokensFloor", 1500),
            }
        except Exception as e:
            return {"reachable": False, "error": str(e)[:120]}

    def _gpu_snapshot(self) -> list[dict]:
        """Return live GPU data with a short cache to avoid expensive helper churn."""
        return self._cached("gpu_snapshot", 5.0, self._gpu_snapshot_uncached)

    def _gpu_snapshot_uncached(self) -> list[dict]:
        try:
            gpu_mon = _get_gpu_monitor()
            gpu_mon.update()
            gpu_list = []
            for idx, g in sorted(gpu_mon.get_gpus().items()):
                gpu_list.append({
                    "index": g.index,
                    "name": g.name,
                    "vendor": g.vendor.value,
                    "temp_c": g.temp,
                    "power_w": g.power_w,
                    "utilization_pct": g.util_percent,
                    "vram_used_gb": g.vram_used_gb,
                    "vram_total_gb": g.vram_total_gb,
                    "fan_percent": g.fan_percent,
                    "pci_slot": g.pci_slot,
                })
            return gpu_list
        except Exception as e:
            print(f"[daemon_client] GPU monitor failed: {e}")
            return []

    def _self_latency_probe(self, proxy_health: Optional[dict] = None) -> dict:
        """Report gateway latency without sending chat completions.

        The old "minimal" ping posted "." to /v1/chat/completions. The chat
        proxy correctly expanded that into ROXY's full brain/RAG prompt, so a
        status refresh became expensive Ada generation. Keep this probe strictly
        non-generating.
        """
        if proxy_health and proxy_health.get("reachable"):
            return {
                "reachable": True,
                "latency_ms": proxy_health.get("health_latency_ms", 0),
                "source": "proxy_health",
                "non_generating": True,
            }
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:4001/health",
                headers={"Content-Type": "application/json"},
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                resp.read()
            t1 = time.time()
            return {
                "reachable": True,
                "latency_ms": round((t1 - t0) * 1000),
                "source": "proxy_health",
                "non_generating": True,
            }
        except Exception as e:
            return {"reachable": False, "error": str(e)[:120], "non_generating": True}
    
    def _local_roxy_snapshot(self, error: str = "") -> dict:
        """Build a non-mutating status snapshot for current ROXY.
        
        Prefers ~/.roxy/apex-status.json (written by emit-apex-status.mjs)
        and merges it with live-local fallback data.
        """
        # Collect live-local data first (always needed for keys apex-status omits)
        law0_ok, law0 = self._run_text_cached(["/opt/roxy/bin/roxy-law0"], timeout=5.0, ttl=30.0)
        guard_ok, guard = self._run_text_cached(["/opt/roxy/bin/roxy-external-guard"], timeout=5.0, ttl=30.0)
        work_ok, work = self._run_text_cached(["findmnt", "/mnt/work"], ttl=30.0)
        df_ok, df = self._run_text_cached(["df", "-hT", "/", "/mnt/work"], ttl=30.0)
        ollama_ok, models, ollama_error = self._ollama_models()
        load = self._load_info()
        memory = self._memory_info()
        cpu_idle = self._cpu_idle_pct()
        cpu_used = max(0.0, 100.0 - cpu_idle)
        failed_units = self._failed_unit_count()
        root_usage = self._usage_for_path("/")
        work_usage = self._usage_for_path("/mnt/work")
        temps = self._temperature_summary()
        gpu_list = self._gpu_snapshot()
        externals = self._external_state()
        workloads = self._active_workloads()

        services = {
            "ollama": self._service_state("ollama.service"),
            "docker": self._service_state("docker.service"),
            "roxy-law0": self._service_state("roxy-law0.service"),
        }
        services["ollama"]["port"] = 11434
        services["ollama"]["port_open"] = ollama_ok
        services["ollama"]["models_loaded"] = [m["name"] for m in models]

        # Try canonical apex-status.json first
        apex_data = self._read_apex_status_json()
        if apex_data:
            # Merge live-local data that apex-status might not have
            apex_data.setdefault("mode", "local")
            # Storage: apex-status.json may omit disk usage; merge live-local
            if not apex_data.get("storage"):
                apex_data["storage"] = {}
            apex_data["storage"].setdefault("root", {})
            apex_data["storage"].setdefault("work", {})
            apex_data["storage"]["root"].update(root_usage)
            apex_data["storage"]["work"].update(work_usage)
            apex_data["storage"]["externals"] = externals
            # hostMemory: keep apex if present, else use live-local
            if not apex_data.get("hostMemory"):
                apex_data["hostMemory"] = {
                    "status": "live",
                    "ram": {
                        "totalGb": memory.get("mem_total_gb", 0),
                        "usedGb": memory.get("mem_used_gb", 0),
                    },
                    "swap": {
                        "totalGb": memory.get("mem_total_gb", 0),  # proxy from available
                        "usedGb": 0,
                    },
                }
            # GPUs: merge live-local GPU data
            if not apex_data.get("gpus"):
                apex_data["gpus"] = gpu_list
            # Roxy guards
            if not apex_data.get("roxy"):
                apex_data["roxy"] = {}
            apex_data["roxy"].setdefault("law0_ok", law0_ok)
            apex_data["roxy"].setdefault("external_guard_ok", guard_ok)
            # Services: merge live-local
            if not apex_data.get("services"):
                apex_data["services"] = services
            # Idle health / temperature
            if not apex_data.get("idle_health"):
                apex_data["idle_health"] = {}
            apex_data["idle_health"].setdefault("temperature", temps)
            # Live brain authority sources (not in apex snapshot)
            apex_data["_live_qdrant"] = self._qdrant_info()
            apex_data["_live_proxy"] = self._proxy_health()
            apex_data["_live_latency"] = self._self_latency_probe(apex_data["_live_proxy"])
            # Alerts
            if error:
                alerts = list(apex_data.get("alerts", []))
                alerts.append({"level": "warning", "message": error})
                apex_data["alerts"] = alerts
            return apex_data
        
        # Fallback: build entirely from local system probes
        law0_ok, law0 = self._run_text_cached(["/opt/roxy/bin/roxy-law0"], timeout=5.0, ttl=30.0)
        guard_ok, guard = self._run_text_cached(["/opt/roxy/bin/roxy-external-guard"], timeout=5.0, ttl=30.0)
        work_ok, work = self._run_text_cached(["findmnt", "/mnt/work"], ttl=30.0)
        df_ok, df = self._run_text_cached(["df", "-hT", "/", "/mnt/work"], ttl=30.0)
        ollama_ok, models, ollama_error = self._ollama_models()
        load = self._load_info()
        memory = self._memory_info()
        cpu_idle = self._cpu_idle_pct()
        cpu_used = max(0.0, 100.0 - cpu_idle)
        failed_units = self._failed_unit_count()
        root_usage = self._usage_for_path("/")
        work_usage = self._usage_for_path("/mnt/work")
        temps = self._temperature_summary()
        gpu_list = self._gpu_snapshot()
        externals = self._external_state()
        workloads = self._active_workloads()

        services = {
            "ollama": self._service_state("ollama.service"),
            "docker": self._service_state("docker.service"),
            "roxy-law0": self._service_state("roxy-law0.service"),
        }
        services["ollama"]["port"] = 11434
        services["ollama"]["port_open"] = ollama_ok
        services["ollama"]["models_loaded"] = [m["name"] for m in models]

        alerts = []
        if not law0_ok:
            alerts.append({"level": "error", "message": "roxy-law0 failed"})
        if not guard_ok:
            alerts.append({"level": "error", "message": "roxy-external-guard failed"})
        if not work_ok:
            alerts.append({"level": "error", "message": "/mnt/work missing"})
        if failed_units:
            alerts.append({"level": "error", "message": f"{failed_units} failed systemd units"})
        if externals["roxy_safety_mounted"]:
            alerts.append({"level": "error", "message": "ROXY_SAFETY is mounted"})
        if error:
            alerts.append({"level": "warning", "message": error})
        if ollama_error:
            alerts.append({"level": "warning", "message": f"Ollama: {ollama_error}"})

        return {
            "mode": "local",
            "system": {
                "cpu_pct": cpu_used,
                "cpu_idle_pct": cpu_idle,
                "load_1m": load["load_1m"],
                "load_5m": load["load_5m"],
                "load_15m": load["load_15m"],
                "logical_cpus": load["logical_cpus"],
                **memory,
            },
            "services": services,
            "ollama": {
                "base_url": OLLAMA_URL,
                "configured": True,
                "reachable": ollama_ok,
                "models": models,
                "error": ollama_error,
            },
            "ollama_models": models,
            "disk": {
                "work_mounted": work_ok,
                "work_findmnt": work,
                "df": df if df_ok else "",
            },
            "storage": {
                "root": {
                    "label": "ROXY_ROOT",
                    "uuid": "52be2027-dd55-4b76-b26e-e4b74bd80e9d",
                    "serial": "S41ZNV0KA00241E",
                    **root_usage,
                },
                "work": {
                    "label": "ROXY_WORK",
                    "uuid": "d151254e-d2dd-4ad3-9e39-e59e59e7a1e9",
                    "serial": "191528800274",
                    **work_usage,
                },
                "externals": externals,
            },
            "gpus": gpu_list,
            "idle_health": {
                "manual_snapshot": True,
                "background_polling": False,
                "cpu_idle_pct": cpu_idle,
                "cpu_used_pct": cpu_used,
                "load_1m": load["load_1m"],
                "load_5m": load["load_5m"],
                "load_15m": load["load_15m"],
                "logical_cpus": load["logical_cpus"],
                "failed_unit_count": failed_units,
                "ollama_active_workloads": workloads["ollama_active_count"],
                "docker_container_count": workloads["docker_container_count"],
                "temperature": temps,
                "samsung_smart_note": "Watch Samsung num_err_log_entries; critical_warning=0 and media_errors=0 in the latest baseline.",
                "status": "quiet" if cpu_idle >= 90 and failed_units == 0 and not externals["roxy_safety_mounted"] else "attention",
            },
            "roxy": {
                "law0_ok": law0_ok,
                "law0_tail": "\n".join(law0.splitlines()[-12:]),
                "external_guard_ok": guard_ok,
                "external_guard_tail": "\n".join(guard.splitlines()[-12:]),
            },
            "alerts": alerts,
        }
    
    def fetch_sync(self) -> DaemonResponse:
        """
        Synchronous fetch (blocking).
        Use sparingly - prefer fetch_async for UI code.
        """
        return self._do_fetch()
    
    def shutdown(self):
        """Clean shutdown of thread pool."""
        self.executor.shutdown(wait=False)


# Global client instance
_client: Optional[DaemonClient] = None

def get_client() -> DaemonClient:
    """Get or create global daemon client."""
    global _client
    if _client is None:
        _client = DaemonClient()
    return _client

def get_status(mode="auto", remote_host="10.0.0.69", remote_port=8766) -> dict:
    """
    Legacy sync interface for backward compatibility.
    Returns dict with status data or error.
    """
    client = get_client()
    client.configure(mode, remote_host, remote_port)
    response = client.fetch_sync()
    
    if response.error:
        return {"error": response.error}
    return response.data

def fetch_status_async(callback: Callable[[DaemonResponse], None], 
                       mode="auto", remote_host="10.0.0.69", remote_port=8766):
    """
    Async fetch interface.
    Callback receives DaemonResponse on main thread.
    """
    client = get_client()
    client.configure(mode, remote_host, remote_port)
    client.fetch_async(callback)


def normalize_status(raw: dict) -> dict:
    """
    Normalize daemon payload to canonical schema.
    Preserves ALL keys from apex-status.json including performance, swarm, lanes,
    brainAuthority, judgeAuthority, and all new ROXY LifePanel data.
    """
    # Start with the full raw payload so nothing is dropped
    result = dict(raw)
    
    # CPU/System — ensure normalized keys exist for backward compat
    sys_data = raw.get("system") or raw.get("stats") or {}
    perf = raw.get("performance") or {}
    perf_cpu = perf.get("cpu") or {}
    cpu = {
        "cpu_pct": sys_data.get("cpu_pct") or raw.get("cpu", {}).get("percent") or perf_cpu.get("utilPct") or 0,
        "load_1m": sys_data.get("load_1m") or perf_cpu.get("load1") or 0,
        "load_5m": sys_data.get("load_5m") or perf_cpu.get("load5") or 0,
        "load_15m": sys_data.get("load_15m") or perf_cpu.get("load15") or 0,
    }
    
    # Memory
    host_ram = (raw.get("hostMemory") or {}).get("ram", {})
    memory = {
        "mem_used_gb": sys_data.get("mem_used_gb") or host_ram.get("usedGb") or host_ram.get("used_gb") or 0,
        "mem_total_gb": sys_data.get("mem_total_gb") or host_ram.get("totalGb") or host_ram.get("total_gb") or 0,
        "mem_available_gb": sys_data.get("mem_available_gb") or host_ram.get("availableGb") or host_ram.get("available_gb") or 0,
    }
    
    # Services
    services = raw.get("services") or {}
    
    # GPUs: accept 'gpu' (list) or 'gpus' (list) or dict
    g = raw.get("gpus") or raw.get("gpu") or (perf.get("gpu") or {}).get("gpus")
    gpus = []
    if isinstance(g, list):
        gpus = g
    elif isinstance(g, dict):
        if all(str(k).isdigit() for k in g.keys()):
            for k in sorted(g.keys(), key=lambda x: int(x)):
                gpus.append(g[k])
        else:
            gpus = [g]
    
    # Normalize each GPU's keys
    norm_gpus = []
    for i, gpu in enumerate(gpus):
        if not isinstance(gpu, dict):
            continue
        vram_used = gpu.get("vram_used_gb") or 0
        vram_total = gpu.get("vram_total_gb") or 16
        if vram_used == 0 and gpu.get("vram_used_bytes"):
            vram_used = gpu.get("vram_used_bytes") / (1024**3)
        if vram_total == 0 and gpu.get("vram_total_bytes"):
            vram_total = gpu.get("vram_total_bytes") / (1024**3)
        if vram_used == 0 and gpu.get("vramUsedMiB"):
            vram_used = gpu.get("vramUsedMiB") / 1024
        if vram_total == 16 and gpu.get("vramTotalMiB"):
            vram_total = gpu.get("vramTotalMiB") / 1024
        
        norm_gpus.append({
            "index": gpu.get("index", i),
            "name": gpu.get("name") or gpu.get("model") or f"GPU {i}",
            "temp_c": gpu.get("temp_c") or gpu.get("tempC") or gpu.get("temp") or gpu.get("temperature_c") or 0,
            "utilization_pct": gpu.get("utilization_pct") or gpu.get("utilPct") or gpu.get("gpu_busy_percent") or gpu.get("util") or 0,
            "vram_used_gb": vram_used,
            "vram_total_gb": vram_total,
            "power_w": gpu.get("power_w") or gpu.get("powerW") or 0,
        })
    
    # Merge normalized backward-compat keys.
    # Always overwrite gpus/cpu/memory with normalized forms to prevent type mismatches.
    result["mode"] = raw.get("mode", "local")
    result["cpu"] = cpu
    result["memory"] = memory
    result["gpus"] = norm_gpus
    result["services"] = services
    result["ollama"] = raw.get("ollama") or {}
    result["disk"] = raw.get("disk") or {}
    result["alerts"] = raw.get("alerts") or []
    result["roxy"] = raw.get("roxy") or {}
    result["storage"] = raw.get("storage") or {}
    result["idle_health"] = raw.get("idle_health") or {}
    result["_raw"] = raw
    
    return result
