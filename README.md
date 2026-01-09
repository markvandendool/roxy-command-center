# ROXY Command Center

GTK4/Libadwaita desktop application for ROXY system monitoring and control.

## Requirements

- Python 3.8+
- GTK4
- Libadwaita
- Working roxy-panel-daemon.py

## Run

```bash
cd ~/roxy-command-center
python3 main.py
```

## Verify

After launching, you should see a window titled "ROXY Command Center" in your screen.

Check it appears in Activities/Alt+Tab:
```bash
wmctrl -l | grep -i roxy
```

Verify CPU usage is low:
```bash
ps aux | grep -E 'main.py|python3.*main' | grep -v grep
```

## Files

- `main.py` - GTK4 application entry point and UI
- `daemon_client.py` - Daemon JSON client
- `README.md` - This file
