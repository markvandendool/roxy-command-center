#!/usr/bin/env python3
"""
TelemetryCollector — rolling metric history for GTK Command Center.

Rule: No decorative telemetry. Every sparkline must be backed by real samples.
If history has < 2 real points, the sparkline renders nothing.
"""

from collections import deque
from typing import Dict, List, Optional


_GLOBAL_COLLECTOR: Optional["TelemetryCollector"] = None


def get_collector() -> "TelemetryCollector":
    global _GLOBAL_COLLECTOR
    if _GLOBAL_COLLECTOR is None:
        _GLOBAL_COLLECTOR = TelemetryCollector()
    return _GLOBAL_COLLECTOR


class TelemetryCollector:
    """
    Maintains rolling deques of system metrics sampled every 5 seconds.
    maxlen=120 → 10 minutes of history at 5s intervals.
    
    Singleton: use get_collector() to access the global instance.
    """

    HISTORY_SIZE = 120  # 120 × 5s = 10 minutes

    METRICS = [
        "cpu",       # CPU utilization %
        "memory",    # RAM used %
        "swap",      # Swap used %
        "thermals",  # Hottest temperature °C
        "gpu0",      # GPU 0 utilization %
        "gpu1",      # GPU 1 utilization %
        "gpu2",      # GPU 2 utilization %
        "network",   # Network throughput MB/s (delta)
        "nvme",      # NVMe IOPS (delta)
        "mcp",       # MCP process count
        "agents",    # Active agent count
    ]

    def __init__(self):
        self._history: Dict[str, deque] = {
            m: deque(maxlen=self.HISTORY_SIZE) for m in self.METRICS
        }
        self._prev: Dict[str, Optional[float]] = {
            "network_rx": None,
            "network_tx": None,
            "nvme_reads": None,
            "nvme_writes": None,
        }

    def push(self, data: dict) -> None:
        """Extract metrics from a daemon response and append to history."""
        perf = data.get("performance") or {}
        host_mem = data.get("hostMemory") or {}
        ram = host_mem.get("ram", {})
        swap = host_mem.get("swap", {})
        gpus = perf.get("gpu", {}).get("gpus", []) if isinstance(perf.get("gpu"), dict) else []
        network = perf.get("network", {})
        nvme = perf.get("nvme", {})
        mcp = perf.get("mcp", {})
        agents = perf.get("agents", {})

        # CPU
        cpu = perf.get("cpu", {}) if isinstance(perf, dict) else {}
        cpu_util = self._num(cpu, "utilPct")
        if cpu_util is not None:
            self._history["cpu"].append(cpu_util)

        # Memory
        ram_total = self._num(ram, "totalGb")
        ram_used = self._num(ram, "usedGb")
        if ram_total and ram_total > 0:
            self._history["memory"].append((ram_used or 0) / ram_total * 100)

        # Swap
        swap_total = self._num(swap, "totalGb")
        swap_used = self._num(swap, "usedGb")
        if swap_total and swap_total > 0:
            self._history["swap"].append((swap_used or 0) / swap_total * 100)

        # Thermals — hottest component temperature
        temps = data.get("idle_health", {}).get("temperature", {})
        if isinstance(temps, dict):
            hottest = temps.get("hottest_c")
            if hottest is not None:
                self._history["thermals"].append(float(hottest))

        # GPUs
        gpu_list = perf.get("gpu", {}) if isinstance(perf, dict) else {}
        if isinstance(gpu_list, dict):
            gpus = gpu_list.get("gpus", [])
        elif isinstance(gpu_list, list):
            gpus = gpu_list
        else:
            gpus = []
        for i in range(3):
            key = f"gpu{i}"
            if i < len(gpus) and isinstance(gpus[i], dict):
                util = gpus[i].get("utilPct") or gpus[i].get("utilization_pct") or gpus[i].get("util")
                if util is not None:
                    self._history[key].append(float(util))
            # If GPU missing, don't append — keeps history from flatlining

        # Network throughput (delta MB/s)
        interfaces = network.get("interfaces", []) if isinstance(network, dict) else []
        total_rx = sum(self._num(iface, "rxBytes") or 0 for iface in interfaces)
        total_tx = sum(self._num(iface, "txBytes") or 0 for iface in interfaces)
        if self._prev["network_rx"] is not None and self._prev["network_tx"] is not None:
            rx_delta = max(0, total_rx - self._prev["network_rx"])
            tx_delta = max(0, total_tx - self._prev["network_tx"])
            mbps = (rx_delta + tx_delta) / (1024 * 1024) / 5.0  # MB/s over 5s
            self._history["network"].append(mbps)
        self._prev["network_rx"] = total_rx
        self._prev["network_tx"] = total_tx

        # NVMe IOPS (delta)
        devices = nvme.get("devices", []) if isinstance(nvme, dict) else []
        total_reads = sum(self._num(dev, "reads") or 0 for dev in devices)
        total_writes = sum(self._num(dev, "writes") or 0 for dev in devices)
        if self._prev["nvme_reads"] is not None and self._prev["nvme_writes"] is not None:
            read_delta = max(0, total_reads - self._prev["nvme_reads"])
            write_delta = max(0, total_writes - self._prev["nvme_writes"])
            iops = (read_delta + write_delta) / 5.0  # ops/s over 5s
            self._history["nvme"].append(iops)
        self._prev["nvme_reads"] = total_reads
        self._prev["nvme_writes"] = total_writes

        # MCP count
        mcp_total = self._num(mcp, "total")
        if mcp_total is not None:
            self._history["mcp"].append(mcp_total)

        # Agents active
        agents_active = self._num(agents, "active")
        if agents_active is not None:
            self._history["agents"].append(agents_active)

    def get(self, metric: str) -> List[float]:
        """Return copy of history for a metric."""
        return list(self._history.get(metric, deque()))

    def has_real_history(self, metric: str, min_points: int = 2) -> bool:
        """True if metric has enough real samples to draw a sparkline."""
        return len(self._history.get(metric, deque())) >= min_points

    def count(self, metric: str) -> int:
        return len(self._history.get(metric, deque()))

    @staticmethod
    def _num(obj: dict, *keys: str) -> Optional[float]:
        for k in keys:
            v = obj.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None
