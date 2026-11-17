#!/bin/sh
# Remove WiFi Fortress installed from source (not via the .deb).
#
#   sudo ./packaging/debian/uninstall.sh
#
# User data (databases, reports, logs) is kept unless you pass --purge.
set -eu

PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this with sudo." >&2
    exit 1
fi

rm -f /usr/bin/wifi-fortress
rm -f /usr/share/applications/wifi-fortress.desktop
rm -f /usr/share/icons/hicolor/scalable/apps/wifi-fortress.svg
rm -rf /opt/wifi-fortress
update-desktop-database -q /usr/share/applications 2>/dev/null || true
echo "WiFi Fortress removed."

if [ "$PURGE" -eq 1 ]; then
    for user_home in /root /home/*; do
        [ -d "$user_home" ] || continue
        rm -rf "$user_home/.local/share/wififortress" \
               "$user_home/.config/wififortress" \
               "$user_home/.cache/wififortress"
    done
    echo "User data purged."
else
    echo "User data kept (pass --purge to delete it)."
fi
