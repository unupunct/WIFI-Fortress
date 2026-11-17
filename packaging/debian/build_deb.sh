#!/bin/sh
# Build a Debian package (.deb) for WiFi Fortress.
#
#   ./packaging/debian/build_deb.sh
#
# Produces packaging/debian/wifi-fortress_<version>_all.deb in the current
# directory. Needs only dpkg-deb (fakeroot is optional but recommended).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VERSION=$(python3 -c "import re,pathlib;print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('$ROOT/wififortress/__init__.py').read_text()).group(1))")
PKG=wifi-fortress
STAGE="$ROOT/packaging/debian/stage"
OUT="$ROOT/packaging/debian/${PKG}_${VERSION}_all.deb"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/opt/wifi-fortress" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/doc/$PKG"

# -- payload ---------------------------------------------------------------
cp -a "$ROOT/wififortress" "$STAGE/opt/wifi-fortress/"
cp "$ROOT/run.py" "$STAGE/opt/wifi-fortress/"
cp "$ROOT/requirements.txt" "$STAGE/opt/wifi-fortress/" 2>/dev/null || true
find "$STAGE/opt/wifi-fortress" -name '__pycache__' -type d -prune -exec rm -rf {} +

install -m 0755 "$ROOT/packaging/debian/wifi-fortress-launcher" "$STAGE/usr/bin/wifi-fortress"
install -m 0644 "$ROOT/packaging/debian/wifi-fortress.desktop" \
    "$STAGE/usr/share/applications/wifi-fortress.desktop"
install -m 0644 "$ROOT/packaging/debian/wifi-fortress.svg" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps/wifi-fortress.svg"
install -m 0644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/README.md"
install -m 0644 "$ROOT/packaging/debian/copyright" "$STAGE/usr/share/doc/$PKG/copyright"
install -m 0644 "$ROOT/packaging/debian/changelog" \
    "$STAGE/usr/share/doc/$PKG/changelog" 2>/dev/null || true

# -- control ---------------------------------------------------------------
INSTALLED_SIZE=$(du -sk "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Maintainer: WiFi Fortress Project <unupunct@users.noreply.github.com>
Depends: python3 (>= 3.12), python3-pyside6.qtwidgets | python3-pyside6, python3-reportlab
Recommends: iw, network-manager, rfkill, ethtool, pciutils, usbutils, python3-pyqtgraph
Suggests: aircrack-ng, kismet, hcxdumptool, wireshark-common, mdk4
Homepage: https://github.com/unupunct/WIFI-Fortress
Description: Wireless security, diagnostics and Wi-Fi recovery suite for Parrot OS
 WiFi Fortress consolidates adapter management, Wi-Fi discovery, authorised
 credential recovery, defensive security auditing, password assessment,
 dictionary management, connection diagnostics and reporting into one
 desktop application.
 .
 The graphical application runs as your normal user and asks for elevation
 only for individual operations. It never captures handshakes, never runs
 deauthentication or cracking workflows, and never logs or transmits
 passwords.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
    gtk-update-icon-cache -q -t /usr/share/icons/hicolor 2>/dev/null || true
    # Headless self-check of the installed copy; failures are warnings only.
    if command -v python3 >/dev/null 2>&1; then
        PYTHONPATH=/opt/wifi-fortress python3 -m wififortress.app.main --selftest >/dev/null 2>&1 \
            || echo "wifi-fortress: self-test reported a problem; run 'wifi-fortress --selftest' for details" >&2
    fi
fi
exit 0
POSTINST

cat > "$STAGE/DEBIAN/prerm" <<'PRERM'
#!/bin/sh
set -e
exit 0
PRERM

cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
exit 0
POSTRM

chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/prerm" "$STAGE/DEBIAN/postrm"

# -- build -----------------------------------------------------------------
if command -v fakeroot >/dev/null 2>&1; then
    fakeroot dpkg-deb --build --root-owner-group "$STAGE" "$OUT"
else
    dpkg-deb --build "$STAGE" "$OUT"
fi
rm -rf "$STAGE"
echo "Built: $OUT"
