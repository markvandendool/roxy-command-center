#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="${HOME}/.local/lib/roxy-command-center"
BIN_DIR="${HOME}/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

backup_path() {
  local path="$1"
  if [ -e "$path" ] && [ ! -e "${path}.bak-${STAMP}" ]; then
    cp -a "$path" "${path}.bak-${STAMP}"
  fi
}

python3 - <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
print("GTK4/Adwaita import OK")
PY

mkdir -p "$INSTALL_ROOT" "$BIN_DIR" "$DESKTOP_DIR"

if [ -e "${HOME}/.local/lib/mindsong-rcc/rcc-gtk4.py" ]; then
  backup_path "${HOME}/.local/lib/mindsong-rcc/rcc-gtk4.py"
fi
if [ -e "${BIN_DIR}/rcc" ]; then
  backup_path "${BIN_DIR}/rcc"
fi

tar \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='output' \
  -C "$APP_DIR" -cf - . | tar -C "$INSTALL_ROOT" -xf -

cat > "${BIN_DIR}/rcc-roxy-command-center" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "${INSTALL_ROOT}"
export RCC_PROFILE=friday
export GDK_BACKEND="\${GDK_BACKEND:-x11}"
exec /usr/bin/python3 main.py "\$@"
EOF
chmod 0755 "${BIN_DIR}/rcc-roxy-command-center"

cat > "${DESKTOP_DIR}/roxy-command-center-friday.desktop" <<EOF
[Desktop Entry]
Name=Roxy Command Center (Friday)
Comment=Read-only Friday RCC cockpit
GenericName=System Monitor
Exec=${BIN_DIR}/rcc-roxy-command-center
Icon=${INSTALL_ROOT}/assets/roxy-command-center.svg
Terminal=false
Type=Application
Categories=System;Monitor;Utility;
Keywords=roxy;rcc;friday;mindsong;monitor;ai;
StartupNotify=true
StartupWMClass=org.roxy.CommandCenter
EOF

if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "${DESKTOP_DIR}/roxy-command-center-friday.desktop"
fi

echo "Installed Friday profile to ${INSTALL_ROOT}"
echo "Run:"
echo "  rcc-roxy-command-center"
echo "  RCC_PROFILE=friday ${INSTALL_ROOT}/launch.sh"
echo "Desktop entry:"
echo "  ${DESKTOP_DIR}/roxy-command-center-friday.desktop"
