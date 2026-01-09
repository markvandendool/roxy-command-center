# ROXY Command Center

GTK4/Libadwaita desktop application for ROXY AI workstation monitoring and control.

![GTK4](https://img.shields.io/badge/GTK-4.0-blue)
![Libadwaita](https://img.shields.io/badge/Libadwaita-1.0-green)
![Python](https://img.shields.io/badge/Python-3.8+-yellow)

## Features

- **GPU Monitoring** - Dual AMD GPU support (6900 XT "BIG" / W5700X "FAST")
- **Service Management** - Ollama pools, Roxy services with start/stop/restart
- **Alert System** - Temperature, VRAM, and health thresholds
- **Sleep Button** - Gracefully stops services before system sleep
- **Modern UI** - Native GTK4/Libadwaita with dark mode support

## Requirements

- Python 3.8+
- GTK4 & Libadwaita (`python3-gi`, `gir1.2-adw-1`)
- Working `roxy-panel-daemon.py`

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

### Sleep Button
The moon icon in the header gracefully:
1. Stops Ollama BIG service
2. Stops Ollama FAST service  
3. Waits for GPUs to cool
4. Initiates system suspend

## License

MIT
