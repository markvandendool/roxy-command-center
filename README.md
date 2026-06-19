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
- Current ROXY runtime; `ollama.service` on `127.0.0.1:11434` unlocks the full model panel, but the GTK app can still launch in degraded mode when it is down

## Installation

```bash
# Install dependencies (Debian/Ubuntu)
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

# Clone and run
git clone https://github.com/markvandendool/roxy-command-center.git
cd roxy-command-center
python3 main.py
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
# Launch
python3 main.py

# Or use the launcher
./launch.sh
```

### Review Safety
This adaptation is not installed as a production authority layer. Service
mutations and system sleep are disabled. Ollama is mapped to the current single
service on `127.0.0.1:11434`.

## License

MIT
