# ROXY Command Center

GTK4/Libadwaita desktop application for ROXY AI workstation monitoring and control.

![GTK4](https://img.shields.io/badge/GTK-4.0-blue)
![Libadwaita](https://img.shields.io/badge/Libadwaita-1.0-green)
![Python](https://img.shields.io/badge/Python-3.8+-yellow)

## Features

- **GPU Monitoring** - Current ROXY status view
- **Service Management** - Read-only service status for this review build
- **Alert System** - Temperature, VRAM, and health thresholds
- **Sleep Button** - Disabled in this review build
- **Modern UI** - Native GTK4/Libadwaita with dark mode support

## Requirements

- Python 3.8+
- GTK4 & Libadwaita (`python3-gi`, `gir1.2-adw-1`)
- Current ROXY runtime with `ollama.service` on `127.0.0.1:11434`

## Installation

```bash
# Install dependencies (Debian/Ubuntu)
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

# Clone and run through the exact-instance launcher
git clone https://github.com/markvandendool/roxy-command-center.git
cd roxy-command-center
./launch.sh

# Install the same tracked launcher for GNOME and autostart
./scripts/install-native-launcher.sh
./scripts/install-native-launcher.sh --check
```

## Structure

```
roxy-command-center/
├── main.py              # Application entry point
├── daemon_client.py     # Async daemon communication
├── widgets/             # UI components
│   ├── gpu_card.py      # GPU monitoring cards
│   ├── service_card.py  # Service management cards
│   ├── ollama_panel.py  # Ollama pool tabs
│   └── ...
├── services/            # Backend services
│   ├── alert_manager.py # Alert system
│   └── gpu_monitor.py   # hwmon GPU discovery
├── ui/                  # UI layouts
│   ├── header_bar.py    # Header with sleep button
│   └── navigation.py    # Sidebar navigation
└── styles/custom.css    # Custom styling
```

## Usage

```bash
# Launch or present the one verified native instance
./launch.sh

# Emit exact D-Bus/PID/window/backend health
python3 tools/runtime_check.py native-health
```

### Safety
The native launcher is installed as the process and presentation authority. It
never broad-kills processes: stale recovery requires the exact D-Bus owner PID,
matching UID, executable, canonical cwd, and zero visible native windows before
bounded termination. Service mutations and system sleep remain disabled.

## License

MIT
