#!/usr/bin/env python3
"""
GPU monitor service with dynamic hwmon discovery.
ROXY-CMD-STORY-010: GPU sensor discovery.
"""

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable
from enum import Enum
import json


class GpuVendor(Enum):
    AMD = "amd"
    NVIDIA = "nvidia"
    INTEL = "intel"
    UNKNOWN = "unknown"


@dataclass
class GpuSensors:
    """Discovered sensor paths for a GPU."""
    hwmon_path: Optional[Path] = None
    temp_path: Optional[Path] = None
    power_path: Optional[Path] = None
    fan_path: Optional[Path] = None
    vram_used_path: Optional[Path] = None
    vram_total_path: Optional[Path] = None
    util_path: Optional[Path] = None
    # For nvidia-smi fallback
    nvidia_index: Optional[int] = None


@dataclass
class GpuInfo:
    """Information about a GPU."""
    index: int
    name: str
    vendor: GpuVendor
    pci_slot: str = ""
    sensors: GpuSensors = field(default_factory=GpuSensors)
    # Current readings
    temp: float = 0.0
    power_w: float = 0.0
    util_percent: float = 0.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0
    fan_percent: float = 0.0


class GpuMonitor:
    """
    GPU monitor with dynamic hwmon discovery.
    
    Features:
    - Auto-detect AMD/NVIDIA/Intel GPUs
    - Discover hwmon sensor paths
    - Fall back to nvidia-smi for NVIDIA
    - Periodic polling
    """
    
    HWMON_BASE = Path("/sys/class/hwmon")
    DRM_BASE = Path("/sys/class/drm")
    
    def __init__(self):
        self._gpus: Dict[int, GpuInfo] = {}
        self._callbacks: List[Callable[[Dict[int, GpuInfo]], None]] = []
        self._poll_source_id: Optional[int] = None
        self._poll_interval_ms = 1000
        
        # Initial discovery
        self._discover_gpus()
    
    def _discover_gpus(self):
        """Discover all GPUs in the system."""
        self._gpus.clear()
        
        # Try AMD GPUs via DRM
        self._discover_amd_gpus()
        
        # Try NVIDIA GPUs
        self._discover_nvidia_gpus()
        
        # Try Intel GPUs
        self._discover_intel_gpus()
        
        print(f"[GpuMonitor] Discovered {len(self._gpus)} GPU(s)")
        for idx, gpu in self._gpus.items():
            print(f"  [{idx}] {gpu.name} ({gpu.vendor.value})")
    
    def _discover_amd_gpus(self):
        """Discover AMD GPUs via DRM and hwmon."""
        try:
            # Look for amdgpu cards
            for card_dir in self.DRM_BASE.glob("card*"):
                if not card_dir.is_dir():
                    continue
                
                # Check for amdgpu device
                device_path = card_dir / "device"
                if not device_path.is_symlink():
                    continue
                
                uevent_path = device_path / "uevent"
                if not uevent_path.exists():
                    continue
                
                # Read uevent to check driver
                try:
                    with open(uevent_path) as f:
                        uevent = f.read()
                    if "DRIVER=amdgpu" not in uevent:
                        continue
                except:
                    continue
                
                # Get card index
                card_name = card_dir.name
                match = re.match(r"card(\d+)", card_name)
                if not match:
                    continue
                card_index = int(match.group(1))
                
                # Find hwmon
                hwmon_path = self._find_hwmon_for_device(device_path)
                
                # Get GPU name
                gpu_name = self._get_amd_gpu_name(device_path)
                
                # Get PCI slot
                pci_slot = self._get_pci_slot(device_path)
                
                # Build sensor paths
                sensors = GpuSensors(hwmon_path=hwmon_path)
                
                if hwmon_path:
                    # Temperature (edge temp)
                    for temp_file in hwmon_path.glob("temp*_input"):
                        label_file = temp_file.with_name(temp_file.name.replace("_input", "_label"))
                        if label_file.exists():
                            try:
                                with open(label_file) as f:
                                    label = f.read().strip().lower()
                                if label == "edge" or "edge" in label:
                                    sensors.temp_path = temp_file
                                    break
                            except:
                                pass
                        else:
                            # Use first temp if no label
                            if sensors.temp_path is None:
                                sensors.temp_path = temp_file
                    
                    # Power
                    power_path = hwmon_path / "power1_average"
                    if power_path.exists():
                        sensors.power_path = power_path
                    
                    # Fan
                    fan_path = hwmon_path / "pwm1"
                    if fan_path.exists():
                        sensors.fan_path = fan_path
                
                # VRAM via DRM
                vram_used = device_path / "mem_info_vram_used"
                vram_total = device_path / "mem_info_vram_total"
                if vram_used.exists():
                    sensors.vram_used_path = vram_used
                if vram_total.exists():
                    sensors.vram_total_path = vram_total
                
                # GPU utilization via DRM
                busy_percent = device_path / "gpu_busy_percent"
                if busy_percent.exists():
                    sensors.util_path = busy_percent
                
                gpu = GpuInfo(
                    index=card_index,
                    name=gpu_name,
                    vendor=GpuVendor.AMD,
                    pci_slot=pci_slot,
                    sensors=sensors
                )
                
                self._gpus[card_index] = gpu
                
        except Exception as e:
            print(f"[GpuMonitor] AMD discovery error: {e}")
    
    def _discover_nvidia_gpus(self):
        """Discover NVIDIA GPUs via nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,name,pci.bus_id,memory.total", 
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode != 0:
                return
            
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 4:
                    continue
                
                nvidia_index = int(parts[0])
                name = parts[1]
                pci_bus = parts[2]
                vram_total = float(parts[3]) / 1024  # MB to GB
                
                # Use a unique index for nvidia
                # Start from 100 to avoid collision with AMD
                internal_index = 100 + nvidia_index
                
                sensors = GpuSensors(nvidia_index=nvidia_index)
                
                gpu = GpuInfo(
                    index=internal_index,
                    name=name,
                    vendor=GpuVendor.NVIDIA,
                    pci_slot=pci_bus,
                    sensors=sensors,
                    vram_total_gb=vram_total
                )
                
                self._gpus[internal_index] = gpu
                
        except FileNotFoundError:
            pass  # nvidia-smi not found
        except Exception as e:
            print(f"[GpuMonitor] NVIDIA discovery error: {e}")
    
    def _discover_intel_gpus(self):
        """Discover Intel GPUs via i915."""
        try:
            for card_dir in self.DRM_BASE.glob("card*"):
                if not card_dir.is_dir():
                    continue
                
                device_path = card_dir / "device"
                uevent_path = device_path / "uevent"
                
                if not uevent_path.exists():
                    continue
                
                try:
                    with open(uevent_path) as f:
                        uevent = f.read()
                    if "DRIVER=i915" not in uevent and "DRIVER=xe" not in uevent:
                        continue
                except:
                    continue
                
                card_name = card_dir.name
                match = re.match(r"card(\d+)", card_name)
                if not match:
                    continue
                card_index = int(match.group(1))
                
                # Skip if already discovered (AMD takes priority)
                if card_index in self._gpus:
                    continue
                
                hwmon_path = self._find_hwmon_for_device(device_path)
                
                sensors = GpuSensors(hwmon_path=hwmon_path)
                
                if hwmon_path:
                    temp_path = hwmon_path / "temp1_input"
                    if temp_path.exists():
                        sensors.temp_path = temp_path
                
                gpu = GpuInfo(
                    index=card_index,
                    name="Intel Graphics",
                    vendor=GpuVendor.INTEL,
                    sensors=sensors
                )
                
                self._gpus[card_index] = gpu
                
        except Exception as e:
            print(f"[GpuMonitor] Intel discovery error: {e}")
    
    def _find_hwmon_for_device(self, device_path: Path) -> Optional[Path]:
        """Find hwmon directory for a device."""
        hwmon_dir = device_path / "hwmon"
        if not hwmon_dir.exists():
            return None
        
        for hwmon in hwmon_dir.iterdir():
            if hwmon.is_dir() and hwmon.name.startswith("hwmon"):
                return hwmon
        
        return None
    
    def _get_amd_gpu_name(self, device_path: Path) -> str:
        """Get AMD GPU name from marketing name or product."""
        # Try marketing name first
        marketing = device_path / "product_name"
        if marketing.exists():
            try:
                with open(marketing) as f:
                    return f.read().strip()
            except:
                pass
        
        # Try vendor/device ID lookup
        vendor_path = device_path / "vendor"
        device_id_path = device_path / "device"
        
        if vendor_path.exists() and device_id_path.exists():
            try:
                with open(vendor_path) as f:
                    vendor = f.read().strip()
                with open(device_id_path) as f:
                    device = f.read().strip()
                return f"AMD GPU ({vendor}:{device})"
            except:
                pass
        
        return "AMD GPU"
    
    def _get_pci_slot(self, device_path: Path) -> str:
        """Get PCI slot from device path."""
        try:
            resolved = device_path.resolve()
            # Path looks like /sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0
            parts = str(resolved).split("/")
            for part in reversed(parts):
                if re.match(r"\d{4}:\d{2}:\d{2}\.\d", part):
                    return part
        except:
            pass
        return ""
    
    def _read_sensor(self, path: Optional[Path]) -> Optional[float]:
        """Read a sensor value from sysfs."""
        if path is None or not path.exists():
            return None
        try:
            with open(path) as f:
                return float(f.read().strip())
        except:
            return None
    
    def _update_amd_gpu(self, gpu: GpuInfo):
        """Update readings for an AMD GPU."""
        sensors = gpu.sensors
        
        # Temperature (millidegrees to degrees)
        temp = self._read_sensor(sensors.temp_path)
        if temp is not None:
            gpu.temp = temp / 1000.0
        
        # Power (microwatts to watts)
        power = self._read_sensor(sensors.power_path)
        if power is not None:
            gpu.power_w = power / 1000000.0
        
        # VRAM (bytes to GB)
        vram_used = self._read_sensor(sensors.vram_used_path)
        vram_total = self._read_sensor(sensors.vram_total_path)
        if vram_used is not None:
            gpu.vram_used_gb = vram_used / (1024**3)
        if vram_total is not None:
            gpu.vram_total_gb = vram_total / (1024**3)
        
        # Utilization (already percentage)
        util = self._read_sensor(sensors.util_path)
        if util is not None:
            gpu.util_percent = util
        
        # Fan (0-255 to percentage)
        fan = self._read_sensor(sensors.fan_path)
        if fan is not None:
            gpu.fan_percent = (fan / 255.0) * 100.0
    
    def _update_nvidia_gpu(self, gpu: GpuInfo):
        """Update readings for an NVIDIA GPU via nvidia-smi."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "-i", str(gpu.sensors.nvidia_index),
                 "--query-gpu=temperature.gpu,power.draw,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            
            if result.returncode != 0:
                return
            
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                gpu.temp = float(parts[0]) if parts[0] != "[Not Supported]" else 0
                gpu.power_w = float(parts[1]) if parts[1] != "[Not Supported]" else 0
                gpu.util_percent = float(parts[2]) if parts[2] != "[Not Supported]" else 0
                gpu.vram_used_gb = float(parts[3]) / 1024 if parts[3] != "[Not Supported]" else 0
                gpu.vram_total_gb = float(parts[4]) / 1024 if parts[4] != "[Not Supported]" else 0
                
        except Exception as e:
            print(f"[GpuMonitor] NVIDIA update error: {e}")
    
    def update(self):
        """Update all GPU readings."""
        for gpu in self._gpus.values():
            if gpu.vendor == GpuVendor.AMD:
                self._update_amd_gpu(gpu)
            elif gpu.vendor == GpuVendor.NVIDIA:
                self._update_nvidia_gpu(gpu)
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(dict(self._gpus))
            except Exception as e:
                print(f"[GpuMonitor] Callback error: {e}")
    
    def get_gpus(self) -> Dict[int, GpuInfo]:
        """Get current GPU info."""
        return dict(self._gpus)
    
    def add_callback(self, callback: Callable[[Dict[int, GpuInfo]], None]):
        """Add update callback."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback):
        """Remove callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def start_polling(self, interval_ms: int = 1000):
        """Start periodic polling."""
        self._poll_interval_ms = interval_ms
        self.stop_polling()
        
        def poll():
            self.update()
            return True  # Continue
        
        self._poll_source_id = GLib.timeout_add(interval_ms, poll)
    
    def stop_polling(self):
        """Stop periodic polling."""
        if self._poll_source_id:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None


# Global instance
_gpu_monitor: Optional[GpuMonitor] = None

def get_gpu_monitor() -> GpuMonitor:
    """Get or create global GPU monitor."""
    global _gpu_monitor
    if _gpu_monitor is None:
        _gpu_monitor = GpuMonitor()
    return _gpu_monitor
