#!/bin/sh
# Install WiFi Fortress from a source checkout (no .deb needed).
#
#   sudo ./packaging/debian/install.sh
#
# Copies the application to /opt/wifi-fortress and adds a launcher, a menu
# entry and an icon. Use ./packaging/debian/build_deb.sh for a .deb instead.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DEST=/opt/wifi-fortress

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this with sudo: sudo $0" >&2
    exit 1
fi

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "python3 is required." >&2; exit 1; }

"$PY" - <<'PYCHECK' || { echo "Python 3.12 or newer is required." >&2; exit 1; }
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PYCHECK

for mod in PySide6 reportlab; do
    "$PY" -c "import $mod" 2>/dev/null || {
        echo "Missing Python module: $mod" >&2
        echo "Install it with: sudo apt install python3-pyside6.qtwidgets python3-reportlab" >&2
        exit 1
    }
done

rm -rf "$DEST"
mkdir -p "$DEST"
cp -a "$ROOT/wififortress" "$DEST/"
cp "$ROOT/run.py" "$DEST/"
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +

install -m 0755 "$ROOT/packaging/debian/wifi-fortress-launcher" /usr/bin/wifi-fortress
install -d /usr/share/applications /usr/share/icons/hicolor/scalable/apps
install -m 0644 "$ROOT/packaging/debian/wifi-fortress.desktop" \
    /usr/share/applications/wifi-fortress.desktop
install -m 0644 "$ROOT/packaging/debian/wifi-fortress.svg" \
    /usr/share/icons/hicolor/scalable/apps/wifi-fortress.svg
update-desktop-database -q /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true

echo "Installed to $DEST"
echo "Run 'wifi-fortress' or start 'WiFi Fortress' from the application menu."
PYTHONPATH="$DEST" "$PY" -m wififortress.app.main --selftest || \
    echo "warning: self-test reported a problem (see above)" >&2
