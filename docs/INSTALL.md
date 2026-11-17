# WiFi Fortress — Installation on Parrot OS

Two supported routes: the `.deb` package, or a source checkout. Both end with
the same `/usr/bin/wifi-fortress` launcher and application-menu entry.

## 0. Before you start

You need Parrot OS (or any Debian 12+ derivative) with Python 3.12 or newer:

```bash
python3 --version          # must print 3.12 or higher
```

Your wireless adapter must be recognised by the kernel:

```bash
ip link                    # look for wlan0 / wlp2s0 / wlx...
sudo rfkill list           # make sure Wi-Fi is not blocked
```

## 1. Install the runtime dependencies

```bash
sudo apt update
sudo apt install -y python3-pyside6.qtwidgets python3-reportlab \
                    iw network-manager rfkill ethtool pciutils usbutils
```

| Package | Needed for | Without it |
|---|---|---|
| `python3-pyside6.qtwidgets` | the GUI | the app cannot start |
| `python3-reportlab` | PDF reports | HTML and JSON reports still work |
| `python3-pyqtgraph` (optional) | dashboard charts | charts are drawn with the fallback renderer |
| `iw` | scanning and adapter capabilities | scanning falls back to `nmcli`; capabilities are reported as unknown |
| `network-manager` | saved-credential recovery | recovery reports that no profiles are available |
| `rfkill` | radio block state | block state is reported as unknown |
| `ethtool`, `pciutils`, `usbutils` | driver and chipset detail | those fields show *Unknown — not determinable* |

## 2. Install WiFi Fortress

### From the release package

```bash
wget https://github.com/unupunct/WIFI-Fortress/releases/latest/download/wifi-fortress_1.0.0_all.deb
sudo dpkg -i wifi-fortress_1.0.0_all.deb
sudo apt --fix-broken install      # only if dpkg reports missing dependencies
```

### From source

```bash
git clone https://github.com/unupunct/WIFI-Fortress.git
cd WiFi-Fortress
sudo ./packaging/debian/install.sh
```

The source installer checks the Python version and the required modules before
copying anything, then runs the self-test.

## 3. Verify

```bash
wifi-fortress --selftest
```

Expected output (values vary by machine):

```
WiFi Fortress 1.0.0 self-test
  data directory      : /home/<you>/.local/share/wififortress
  dictionaries        : 10 files, 5414 entries readable
  password assessment : score 62/100 (Fair)
  password generation : 24 characters
  adapters detected   : 1
  tools available     : 7
  result              : OK
```

## 4. Start it

From the application menu: **WiFi Fortress** (category *System / Security*).
From a terminal:

```bash
wifi-fortress
```

> Run it as your normal user. The application asks for elevation only for the
> individual operations that need it, and refuses to start under `sudo`.

## 5. First run checklist

1. **Adapter Manager** → *Refresh* → your adapter is listed and *Monitor mode*
   shows a real answer (supported / not supported / unknown).
2. **Wireless Networks** → *Scan* → networks appear with security classification.
3. **Wi-Fi Recovery** → step 1 lists your adapter, step 3 lists saved profiles.
4. **Security Audit** → pick your own network → a score, findings and a checklist.
5. **Reports** → *Generate* → a PDF opens from the reports folder.

If any of these steps show *Unknown — not determinable* rather than a value,
the corresponding tool from step 1 is missing.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Adapter discovery requires Linux (Parrot OS).` | You are on Windows/macOS. Only the Linux build can talk to the radio. |
| `Neither iw nor nmcli is available` | `sudo apt install iw network-manager` |
| Scan returns nothing | Adapter is down or rfkill-blocked: `sudo ip link set wlan0 up`, `sudo rfkill unblock wifi` |
| `Could not import PySide6` | `sudo apt install python3-pyside6.qtwidgets`, or you are running a different Python than the system one |
| Recovery says no profiles exist | That SSID has no saved profile **for your user**; system-wide profiles need the explicit authorisation checkbox |
| PDF generation fails | `sudo apt install python3-reportlab`; use HTML/JSON meanwhile |
| Charts are missing | optional dependency: `sudo apt install python3-pyqtgraph` |

Logs are written to `~/.local/share/wififortress/logs/` and are redacted: they
never contain passwords.

## Uninstall

```bash
sudo apt remove wifi-fortress          # package install
sudo ./packaging/debian/uninstall.sh   # source install
```

Add `purge` (or `--purge` for the script) to delete your data, reports and logs
as well.
