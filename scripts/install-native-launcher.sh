#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
APPLICATIONS_DIR="$HOME/.local/share/applications"
AUTOSTART_DIR="$HOME/.config/autostart"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_FILE="roxy-command-center.desktop"
ICON_FILE="roxy-command-center.svg"

check_installation() {
    local failures=0
    [[ "$(readlink -f "$BIN_DIR/roxy-command-center" 2>/dev/null || true)" == "$ROOT/launch.sh" ]] || failures=$((failures + 1))
    [[ "$(readlink -f "$BIN_DIR/roxy-command-center-gwd" 2>/dev/null || true)" == "$ROOT/launch_gwd.sh" ]] || failures=$((failures + 1))
    cmp -s "$ROOT/$DESKTOP_FILE" "$APPLICATIONS_DIR/$DESKTOP_FILE" || failures=$((failures + 1))
    cmp -s "$ROOT/$DESKTOP_FILE" "$AUTOSTART_DIR/$DESKTOP_FILE" || failures=$((failures + 1))
    cmp -s "$ROOT/assets/$ICON_FILE" "$ICON_DIR/$ICON_FILE" || failures=$((failures + 1))

    if (( failures > 0 )); then
        printf 'RCC_NATIVE_INSTALL_DRIFT failures=%s\n' "$failures"
        return 1
    fi
    printf 'RCC_NATIVE_INSTALL_CURRENT root=%s\n' "$ROOT"
}

if [[ "${1:-}" == "--check" ]]; then
    check_installation
    exit
fi

mkdir -p "$BIN_DIR" "$APPLICATIONS_DIR" "$AUTOSTART_DIR" "$ICON_DIR"
ln -sfn "$ROOT/launch.sh" "$BIN_DIR/roxy-command-center"
ln -sfn "$ROOT/launch_gwd.sh" "$BIN_DIR/roxy-command-center-gwd"
install -m 0644 "$ROOT/$DESKTOP_FILE" "$APPLICATIONS_DIR/$DESKTOP_FILE"
install -m 0644 "$ROOT/$DESKTOP_FILE" "$AUTOSTART_DIR/$DESKTOP_FILE"
install -m 0644 "$ROOT/assets/$ICON_FILE" "$ICON_DIR/$ICON_FILE"

desktop-file-validate "$APPLICATIONS_DIR/$DESKTOP_FILE"
desktop-file-validate "$AUTOSTART_DIR/$DESKTOP_FILE"
check_installation
